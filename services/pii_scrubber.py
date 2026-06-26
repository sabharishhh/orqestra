"""
PII scrubbing with per-organization allowlist support.

Each org defines its own clinical/business vocabulary in the
`pii_allowlist` table (seeded from `presets/<vertical>.yaml`). The
scrubber preserves overlapping terms (e.g., a clinical org keeps
"EGFR" even though spaCy flags it as ORG) while redacting PERSON,
ORG, and GPE entities outside the allowlist, plus SSN and phone
number patterns via regex.
"""
import re
import logging
import subprocess
from typing import Optional, Union, Set
from uuid import UUID

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    import spacy
    nlp = spacy.load("en_core_web_sm")

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import PiiAllowlistToken
from services.config_loader import _redis, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# Built-in fallback. Applied when an org has no pii_allowlist rows,
# or when the scrubber is called without an org_id (legacy pipeline
# entry points that haven't been threaded through yet). Mirrors the
# pre-multitenant constant so behavior is unchanged in that path.
DEFAULT_ALLOWLIST: Set[str] = {
    "mg", "ml", "kg", "egfr", "cpt", "icd",
    "dosage", "blood pressure", "bpm", "dose",
}

# Compiled once at module load
_SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_PHONE_RE = re.compile(r'\b\d{3}-\d{3}-\d{4}\b')
_REDACTED_ENT_LABELS = {"PERSON", "ORG", "GPE"}


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
            return set(cached.split("|"))
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
            logger.info(f"No pii_allowlist rows for org {org_id}. Using built-in defaults.")
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
    """Drop cached allowlist after admin edits PII tokens (Sprint 5 admin UI)."""
    try:
        _redis.delete(_allowlist_cache_key(str(org_id)))
        logger.info(f"Invalidated PII allowlist cache for org {org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate allowlist cache: {e}")


def scrub_pii(text: str, org_id: Optional[Union[str, UUID]] = None) -> str:
    """
    Redact PII from a string using NER + regex, preserving terms in the
    org's allowlist.

    Args:
        org_id: tenant scope. When None, applies the built-in DEFAULT_ALLOWLIST.
                Pre-multitenant callers (e.g. workers/tasks.process_sample_task)
                may invoke without org_id; Sprint 5+ callers should always pass it.
    """
    allowlist = _load_allowlist(str(org_id)) if org_id is not None else DEFAULT_ALLOWLIST

    # Regex redactions first — these don't interact with NER
    scrubbed = _SSN_RE.sub('[REDACTED_SSN]', text)
    scrubbed = _PHONE_RE.sub('[REDACTED_PHONE]', scrubbed)

    # NER pass — preserve entities overlapping with the allowlist
    doc = nlp(scrubbed)
    for ent in doc.ents:
        if ent.label_ not in _REDACTED_ENT_LABELS:
            continue
        ent_lower = ent.text.lower()
        if any(term in ent_lower for term in allowlist):
            continue
        scrubbed = scrubbed.replace(ent.text, f"[REDACTED_{ent.label_}]")

    return scrubbed