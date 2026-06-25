"""
Per-organization entity hint canonicalization.

Maps free-form `entity_hint` strings (emitted by the extraction LLM) to
the canonical names registered in canonical_entities for a given org.

Two-stage resolution:
  Stage 1: Exact alias lookup against the org's `entity_aliases` table
           (Redis-cached, O(1) hash lookup once warm).
  Stage 2: Semantic nearest-neighbor against existing OBG centroids using
           pgvector's HNSW cosine-distance operator (O(log n)).

If neither stage finds a match, the normalized raw hint is returned as-is.
Auto-induction (workers/auto_induction.py) will eventually cluster these
orphans into candidates for promotion to canonical.
"""
import json
import logging
from typing import Optional, Union
from uuid import UUID

from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import CanonicalEntity, EntityAlias
from services.config_loader import (
    get_org_config,
    _redis,
    CACHE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)


def _alias_map_cache_key(org_id: str) -> str:
    return f"orqestra:aliasmap:{org_id}"


def _load_alias_map(org_id: str, db: Session) -> dict[str, str]:
    """
    Returns {alias: canonical_name} for an org. Includes self-mappings so
    canonical names also resolve to themselves. Cached in Redis.

    For an org with ~10 canonical entities and ~50 aliases, this map is
    ~3 KB serialized — negligible memory. For 1000 entities / 10K aliases,
    still under 1 MB. We can switch to per-alias caching if that breaks down.
    """
    cache_key = _alias_map_cache_key(org_id)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    rows = db.execute(
        select(EntityAlias.alias, CanonicalEntity.canonical_name)
        .join(CanonicalEntity, EntityAlias.canonical_entity_id == CanonicalEntity.id)
        .where(EntityAlias.org_id == org_id)
    ).all()

    mapping: dict[str, str] = {alias: canon for alias, canon in rows}

    # Self-mappings — canonical names resolve to themselves
    canonical_names = db.execute(
        select(CanonicalEntity.canonical_name).where(CanonicalEntity.org_id == org_id)
    ).scalars().all()
    for c in canonical_names:
        mapping[c] = c

    try:
        _redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(mapping))
    except Exception as e:
        logger.warning(f"Redis write failed for {cache_key}: {e}")

    return mapping


def _semantic_resolve(
    org_id: str,
    normalized: str,
    embedding: list,
    db: Session,
) -> Optional[str]:
    """
    Stage 2: find the canonical entity whose OBG centroid is closest to
    the new claim's embedding. Uses pgvector's HNSW cosine-distance index
    on entity_belief_states.centroid_embedding — O(log n) lookup.

    Threshold for accepting a semantic match comes from
    DetectionConfig.semantic_match_threshold (default 0.55 = similarity).
    """
    cfg = get_org_config(org_id, db)
    threshold = cfg.semantic_match_threshold  # similarity, e.g. 0.55

    # pgvector uses cosine *distance* (1 - similarity).
    # We want similarity >= threshold, i.e. distance <= (1 - threshold).
    max_distance = 1.0 - threshold

    # Raw SQL because SQLAlchemy + pgvector ORM operators are awkward for
    # the cast + ordering pattern. The HNSW index is hit via the <=> op.
    query = sql_text("""
        SELECT
          obg.entity_name,
          (obg.centroid_embedding <=> CAST(:emb AS vector)) AS distance
        FROM entity_belief_states obg
        JOIN canonical_entities ce
          ON ce.org_id = :org_id
         AND ce.canonical_name = obg.entity_name
        WHERE obg.org_id = :org_id
          AND obg.sample_count >= 1
          AND obg.centroid_embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT 1
    """)

    result = db.execute(query, {
        "org_id": org_id,
        "emb": str(embedding),  # pgvector accepts the textual list form
    }).first()

    if result is None:
        return None

    canonical, distance = result.entity_name, result.distance
    if distance is None or distance > max_distance:
        return None

    similarity = 1.0 - distance
    logger.info(
        f"[{org_id}] semantic resolve: '{normalized}' → '{canonical}' "
        f"(similarity={similarity:.3f} >= threshold={threshold})"
    )
    return canonical


def resolve_entity_hint(
    org_id: Union[str, UUID],
    raw_hint: str,
    embedding: Optional[list] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Resolve a free-form entity_hint to a canonical name for an org.

    Args:
        org_id: tenant scope (UUID or string)
        raw_hint: the LLM's free-form entity_hint (e.g. 'meal_plan_requirements')
        embedding: claim embedding for Stage 2 semantic fallback (optional)
        db: optional session — if provided, skips opening one

    Returns:
        Canonical name if Stage 1 or 2 resolved; otherwise the normalized
        raw hint (for auto-induction to cluster later).
    """
    if not raw_hint:
        return "general"

    org_id_str = str(org_id)
    normalized = raw_hint.lower().strip().replace(" ", "_").replace("-", "_")

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # Stage 1: exact alias lookup
        alias_map = _load_alias_map(org_id_str, db)
        if normalized in alias_map:
            canonical = alias_map[normalized]
            if canonical != normalized:
                logger.info(f"[{org_id_str}] alias: '{normalized}' → '{canonical}'")
            return canonical

        # Stage 2: semantic nearest-neighbor (only if we have an embedding)
        if embedding is not None:
            canonical = _semantic_resolve(org_id_str, normalized, embedding, db)
            if canonical:
                return canonical

        # Unresolved — return normalized, let auto-induction handle it
        logger.info(f"[{org_id_str}] unknown entity hint: '{normalized}' (kept as orphan)")
        return normalized
    finally:
        if own_session:
            db.close()


def invalidate_alias_cache(org_id: Union[str, UUID]) -> None:
    """Drop the cached alias map for an org. Call after CanonicalEntity edits."""
    try:
        _redis.delete(_alias_map_cache_key(str(org_id)))
        logger.info(f"Invalidated alias map cache for org {org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate alias cache for {org_id}: {e}")


# =====================================================
# Backward-compatibility shim for pre-multitenant callers.
# Removed in Sprint 3.2 once workers pass org_id explicitly.
# =====================================================
def _resolve_legacy(
    raw_hint: str,
    embedding: Optional[list] = None,
    db: Optional[Session] = None,
) -> str:
    """
    Legacy single-tenant call site. Looks up the demo-fitness org and
    delegates. DO NOT add new callers — pass org_id explicitly.
    """
    from services.config_loader import get_org_id_by_slug
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        org_id = get_org_id_by_slug("demo-fitness", db)
        if org_id is None:
            logger.warning("Legacy resolve_entity_hint called but demo-fitness org not seeded")
            return raw_hint.lower().strip().replace(" ", "_").replace("-", "_") if raw_hint else "general"
        return resolve_entity_hint(org_id, raw_hint, embedding=embedding, db=db)
    finally:
        if own_session:
            db.close()