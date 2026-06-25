"""
Per-organization severity and cost resolution.

Replaces the hardcoded severity-bucket function in contradiction_detector.py
and the hardcoded $1,200/$150 cost constants in resolution_agent.py and
roi.py with a data-driven service that reads from the canonical_entities
table.

Severity tier and dollar cost are joint properties of:
  - The canonical entity (its declared severity_tier and cost coefficients)
  - The NLI confidence score on the specific contradiction (modulates within tier)

This is the single point where "how bad is this contradiction, and how much
does it cost" is computed across the codebase.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional, Union
from uuid import UUID

from redis import Redis
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import CanonicalEntity
from services.config_loader import get_org_config, _redis, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# =====================================================
# Fallback severity & cost for unknown entities
# Applied when a contradiction names an entity_hint that isn't in the
# org's canonical_entities table. Keeps the pipeline running even when
# the LLM emits a brand-new hint that hasn't been canonicalized yet.
# =====================================================
UNKNOWN_ENTITY_DEFAULT = {
    "severity_tier": "low",
    "cost_high_usd": 100,
    "cost_critical_usd": 500,
}


@dataclass
class SeverityResult:
    severity: str            # 'critical' | 'high' | 'medium' | 'low'
    cost_usd: int            # dollar exposure estimate
    entity_tier: str         # declared tier of the canonical entity
    confidence_used: float   # NLI confidence that fed this decision


def _entity_cache_key(org_id: str, canonical_name: str) -> str:
    return f"orqestra:entity:{org_id}:{canonical_name}"


def _load_entity_meta(org_id: str, canonical_name: str, db: Optional[Session] = None) -> dict:
    """
    Returns {severity_tier, cost_high_usd, cost_critical_usd, importance, category}
    for a canonical entity. Cached in Redis with the same TTL as org config.
    """
    cache_key = _entity_cache_key(org_id, canonical_name)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = (db.query(CanonicalEntity)
                 .filter_by(org_id=org_id, canonical_name=canonical_name)
                 .first())
        if row is None:
            meta = {**UNKNOWN_ENTITY_DEFAULT, "importance": 0.3, "category": "general"}
        else:
            meta = {
                "severity_tier":     row.severity_tier,
                "cost_high_usd":     row.cost_high_usd,
                "cost_critical_usd": row.cost_critical_usd,
                "importance":        row.importance,
                "category":          row.category,
            }
        try:
            _redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(meta))
        except Exception as e:
            logger.warning(f"Redis write failed for {cache_key}: {e}")
        return meta
    finally:
        if own_session:
            db.close()


def invalidate_entity_meta(org_id: Union[str, UUID], canonical_name: Optional[str] = None) -> None:
    """
    Drop a cached entity (or all entities for an org if canonical_name is None).
    Call after admin edits a CanonicalEntity row.
    """
    try:
        if canonical_name:
            _redis.delete(_entity_cache_key(str(org_id), canonical_name))
        else:
            pattern = f"orqestra:entity:{org_id}:*"
            for key in _redis.scan_iter(match=pattern):
                _redis.delete(key)
        logger.info(f"Invalidated entity cache for org={org_id} entity={canonical_name or 'ALL'}")
    except Exception as e:
        logger.warning(f"Failed to invalidate entity cache: {e}")


def calculate_severity_and_cost(
    org_id: Union[str, UUID],
    canonical_entity: str,
    nli_confidence: float,
    db: Optional[Session] = None,
) -> SeverityResult:
    """
    Resolve (severity, cost_usd) for a contradiction.

    The canonical entity declares its severity tier (critical/high/medium/low)
    and its dollar weight at high vs critical severity. The NLI confidence
    modulates: if confidence is below the org's floor, the contradiction
    gets demoted by one tier even if the entity is declared critical.

    Args:
        org_id: tenant scope
        canonical_entity: the resolved canonical name (post-entity-resolver)
        nli_confidence: Level 4 confidence, range [0.0, 1.0]
        db: optional session — if provided, skips opening one
    """
    org_id_str = str(org_id)
    cfg = get_org_config(org_id_str, db)
    meta = _load_entity_meta(org_id_str, canonical_entity, db)

    floor = cfg.nli_confidence_floor
    declared_tier = meta["severity_tier"]

    # Below NLI floor — demote one tier regardless of declared severity.
    # This stops a low-confidence "critical" entity match from triggering
    # a $500K alert in clinical or $1.2K in consumer just because the
    # entity itself is high-stakes.
    if nli_confidence < floor:
        if declared_tier == "critical":
            effective = "high"
        elif declared_tier == "high":
            effective = "medium"
        elif declared_tier == "medium":
            effective = "low"
        else:
            effective = "low"
    else:
        # At or above floor — entity's declared tier holds, but confidence
        # within the tier shifts cost. Above 0.85 keeps full cost; between
        # floor and 0.85 keeps tier but at 70% cost.
        effective = declared_tier

    # Cost mapping
    if effective == "critical":
        cost = meta["cost_critical_usd"]
    elif effective == "high":
        cost = meta["cost_high_usd"]
    elif effective == "medium":
        cost = meta["cost_high_usd"] // 2
    else:
        cost = meta["cost_high_usd"] // 10

    # Confidence drag within tier
    if effective != "low" and nli_confidence < 0.85 and nli_confidence >= floor:
        cost = int(cost * 0.7)

    return SeverityResult(
        severity=effective,
        cost_usd=cost,
        entity_tier=declared_tier,
        confidence_used=nli_confidence,
    )