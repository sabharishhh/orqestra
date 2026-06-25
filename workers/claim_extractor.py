import os
import json
import logging
from typing import List, Dict, Any

import httpx
from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import CanonicalEntity, System
from services.config_loader import _redis, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# =====================================================
# Dynamic per-org extraction prompt
# =====================================================
_PROMPT_HEADER = """You are a precise operational data extraction engine.
Your task is to decompose raw text into an explicit array of factual claims represented as Subject-Predicate-Object (SPO) triples with a strict contextual modifier.

CRITICAL: For each claim, you MUST set `entity_hint` to ONE value from this CLOSED vocabulary. Do not invent new hints. Pick the single closest match:

ALLOWED entity_hint values:
"""

_PROMPT_FOOTER = """- general                (only when nothing else fits)

Return ONLY JSON matching:
{
  "claims": [
    {
      "subject": "string",
      "predicate": "string",
      "object": "string",
      "context": "string",
      "entity_hint": "string (MUST be from the allowed list above)"
    }
  ]
}"""


def _prompt_cache_key(org_id: str) -> str:
    return f"orqestra:extraction_prompt:{org_id}"


def _resolve_org_id_from_system(db: Session, system_id: str) -> str:
    row = db.query(System.org_id).filter(System.id == system_id).first()
    if row is None:
        raise RuntimeError(f"System {system_id} has no org_id — Sprint 1.3 backfill missing?")
    return str(row.org_id)


def _build_extraction_prompt(org_id: str, db: Session) -> str:
    """
    Build the EXTRACTION_SYSTEM_PROMPT dynamically from the org's
    canonical_entities. Cached in Redis with the same TTL as org config —
    invalidated when admin edits canonical entities (Sprint 5.x).
    """
    cache_key = _prompt_cache_key(org_id)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return cached
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    entities = (
        db.query(CanonicalEntity)
          .filter_by(org_id=org_id)
          .order_by(CanonicalEntity.canonical_name)
          .all()
    )

    if not entities:
        # Org has no canonical entities seeded — every hint becomes 'general'.
        # The extractor still works; auto-induction will cluster orphans later.
        logger.warning(
            f"No canonical entities for org {org_id}. Extraction prompt will only "
            f"allow 'general' hints. Run scripts.seed_org to populate."
        )
        allowed_block = ""
    else:
        # Compose the ALLOWED block. Use description if present; otherwise
        # synthesize a fallback from the name itself for the LLM to anchor on.
        lines = []
        for e in entities:
            note = e.description or e.canonical_name.replace("_", " ")
            # Pad to the widest name so the list is readable in the prompt
            lines.append(f"- {e.canonical_name:<24} ({note})")
        allowed_block = "\n".join(lines) + "\n"

    prompt = _PROMPT_HEADER + allowed_block + _PROMPT_FOOTER

    try:
        _redis.setex(cache_key, CACHE_TTL_SECONDS, prompt)
    except Exception as e:
        logger.warning(f"Redis write failed for {cache_key}: {e}")

    return prompt


def invalidate_extraction_prompt(org_id: str) -> None:
    """Drop cached prompt after admin edits canonical entities."""
    try:
        _redis.delete(_prompt_cache_key(org_id))
        logger.info(f"Invalidated extraction prompt cache for org {org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate extraction prompt cache: {e}")


# =====================================================
# Main extraction entry point
# =====================================================
@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError, httpx.HTTPError)),
    reraise=True,
)
def run_extraction(text: str, system_id: str) -> List[Dict[str, Any]]:
    """
    Worker 1 Phase: Extracts structured SPO triples and generates 1536-dim embeddings.

    Sprint 3.3: system_id is now required so we can resolve org_id and use
    the org's canonical vocabulary in the extraction prompt.
    """
    if not text.strip():
        return []

    db: Session = SessionLocal()
    try:
        org_id = _resolve_org_id_from_system(db, system_id)
        system_prompt = _build_extraction_prompt(org_id, db)
    finally:
        db.close()

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # --- PHASE 1: SPO Extraction ---
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract facts from this text:\n\n{text}"},
        ],
        temperature=0.0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```json"):
        raw = raw[7:-3].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    try:
        claims_data = json.loads(raw).get("claims", [])
    except Exception as e:
        logger.error(f"Failed to parse extraction JSON: {e}")
        return []

    # --- PHASE 2: OpenAI Embeddings ---
    if not claims_data:
        return []

    texts_to_embed = [
        f"{c.get('subject', '')} {c.get('predicate', '')} {c.get('object', '')}. Context: {c.get('context', '')}"
        for c in claims_data
    ]
    emb_response = client.embeddings.create(
        input=texts_to_embed,
        model="text-embedding-3-small",
    )
    embeddings = [data.embedding for data in sorted(emb_response.data, key=lambda x: x.index)]

    embedded_claims = []
    for claim, emb in zip(claims_data, embeddings):
        embedded_claims.append({"claim": claim, "embedding": emb})

    return embedded_claims