import re
import logging
from typing import Optional, Union, Set
from uuid import UUID

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    import spacy
    nlp = spacy.load("en_core_web_sm")

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import PiiAllowlistToken
from services.config_loader import _redis, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# =====================================================
# Fallback allowlist for orgs with no pii_allowlist rows.
# Matches the legacy hardcoded set so behavior is unchanged
# when the table is empty. Real customers override via seed.
# =====================================================
DEFAULT_ALLOWLIST: Set[str] = {
    "mg", "ml", "kg", "egfr", "cpt", "icd",
    "dosage", "blood pressure", "bpm", "dose",
}


def _allowlist_cache_key(org_id: str) -> str:
    return f"orqestra:pii_allowlist:{org_id}"


def _load_allowlist(org_id: str, db: Optional[Session] = None) -> Set[str]:
    """
    Returns the lowercased PII allowlist for an org. Cached in Redis.
    Falls back to DEFAULT_ALLOWLIST if the org has no rows seeded.
    """
    cache_key = _allowlist_cache_key(org_id)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return set(cached.split("|")) if cached else DEFAULT_ALLOWLIST
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        rows = (
            db.query(PiiAllowlistToken.token)
              .filter_by(org_id=org_id)
              .all()
        )
        tokens = {r.token.lower().strip() for r in rows if r.token}
        if not tokens:
            logger.info(f"No pii_allowlist for org {org_id}. Using built-in defaults.")
            tokens = DEFAULT_ALLOWLIST

        try:
            _redis.setex(cache_key, CACHE_TTL_SECONDS, "|".join(sorted(tokens)))
        except Exception as e:
            logger.warning(f"Redis write failed for {cache_key}: {e}")

        return tokens
    finally:
        if own_session:
            db.close()


def invalidate_allowlist_cache(org_id: Union[str, UUID]) -> None:
    """Drop cached allowlist after admin edits PII tokens."""
    try:
        _redis.delete(_allowlist_cache_key(str(org_id)))
        logger.info(f"Invalidated PII allowlist cache for org {org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate allowlist cache: {e}")


def scrub_pii(text: str, org_id: Optional[Union[str, UUID]] = None) -> str:
    """
    F3.4 Compliance: PII scrubber with per-org allowlist and NER.

    Sprint 3.6c: the allowlist is now per-org. Clinical customers see
    medical terms preserved; consumer orgs see only consumer-relevant
    tokens spared. When org_id is None, falls back to the demo-fitness
    org via the shim — pre-multitenant callers continue to work.
    """
    if org_id is None:
        # Legacy single-tenant fallback. Sprint 3.6c+ callers should pass org_id.
        from services.config_loader import get_org_id_by_slug
        org_id = get_org_id_by_slug("demo-fitness")
        if org_id is None:
            allowlist = DEFAULT_ALLOWLIST
        else:
            allowlist = _load_allowlist(str(org_id))
    else:
        allowlist = _load_allowlist(str(org_id))

    doc = nlp(text)
    scrubbed_text = text

    # Simple regex for SSN and Phone
    scrubbed_text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', scrubbed_text)
    scrubbed_text = re.sub(r'\b\d{3}-\d{3}-\d{4}\b', '[REDACTED_PHONE]', scrubbed_text)

    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE"]:
            # Preserve entities that overlap with the org's allowlist
            # (e.g. clinical orgs keep "EGFR" intact even though spaCy
            # sometimes flags it as ORG).
            if not any(term in ent.text.lower() for term in allowlist):
                scrubbed_text = scrubbed_text.replace(ent.text, f"[REDACTED_{ent.label_}]")

    return scrubbed_text