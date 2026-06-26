"""
Per-organization configuration loader.

Reads from the `detection_config` and `organizations` tables, caches the
result in Redis with a short TTL, and exposes a single dataclass that
workers consume in place of hardcoded magic numbers.

Cache invalidation: Sprint 5.x admin UI calls `invalidate_org_config(org_id)`
after any config edit. Cache also expires naturally every CACHE_TTL_SECONDS.

Performance: 95%+ Redis cache hit rate means every claim's worker pipeline
pays a single millisecond-scale Redis GET instead of a DB query per stage.
"""
import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Union
from uuid import UUID

from redis import Redis
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import DetectionConfig, Organization

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes — admin edits propagate quickly enough
_redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


# =====================================================
# Hardcoded fallback defaults
# These mirror the legacy magic numbers and ensure the system keeps
# working even if the DB rows are missing for an org. They match
# presets/consumer.yaml so behavior is identical to pre-refactor.
# =====================================================
DEFAULT_CONFIG = {
    # Funnel
    "bootstrap_min_samples": 3,
    "high_variance_threshold": 0.40,
    "semantic_match_threshold": 0.55,
    # Auto-induction
    "cluster_min_size": 5,
    "cluster_merge_threshold": 0.20,
    "induction_lookback_days": 7,
    "induction_cluster_threshold": 0.35,
    "induction_min_cluster_size": 5,      
    "induction_merge_threshold": 0.20,  
    # Suppression / dedup
    "regression_dedup_days": 7,
    "semantic_suppression_distance": 0.05,
    # Scoring
    "coherence_window_days": 30,
    "recency_decay_lambda": 0.05,
    "nli_confidence_floor": 0.70,
    # Blast-radius (Sprint 5.2)
    "blast_radius_decay": 0.5,
}


@dataclass
class OrgConfig:
    """Resolved per-org config. Construct only via get_org_config()."""
    org_id: str
    # Funnel
    bootstrap_min_samples: int
    high_variance_threshold: float
    semantic_match_threshold: float
    # Auto-induction
    cluster_min_size: int
    cluster_merge_threshold: float
    induction_lookback_days: int
    induction_cluster_threshold: float
    induction_min_cluster_size: int
    induction_merge_threshold: float
    # Suppression / dedup
    regression_dedup_days: int
    semantic_suppression_distance: float
    # Scoring
    coherence_window_days: int
    recency_decay_lambda: float
    nli_confidence_floor: float
    blast_radius_decay: float

    @classmethod
    def from_defaults(cls, org_id: str) -> "OrgConfig":
        return cls(org_id=org_id, **DEFAULT_CONFIG)

    @classmethod
    def from_db_row(cls, org_id: str, row: DetectionConfig) -> "OrgConfig":
        return cls(
            org_id=org_id,
            bootstrap_min_samples=row.bootstrap_min_samples,
            high_variance_threshold=row.high_variance_threshold,
            semantic_match_threshold=row.semantic_match_threshold,
            cluster_min_size=row.cluster_min_size,
            cluster_merge_threshold=row.cluster_merge_threshold,
            induction_lookback_days=row.induction_lookback_days,
            induction_cluster_threshold=row.induction_cluster_threshold,
            induction_min_cluster_size=row.induction_min_cluster_size,    # NEW
            induction_merge_threshold=row.induction_merge_threshold,
            regression_dedup_days=row.regression_dedup_days,
            semantic_suppression_distance=row.semantic_suppression_distance,
            coherence_window_days=row.coherence_window_days,
            recency_decay_lambda=row.recency_decay_lambda,
            nli_confidence_floor=row.nli_confidence_floor,
            blast_radius_decay=row.blast_radius_decay,
        )


def _cache_key(org_id: str) -> str:
    return f"orqestra:cfg:{org_id}"


def get_org_config(org_id: Union[str, UUID], db: Optional[Session] = None) -> OrgConfig:
    """
    Resolve an org's detection config. Cached in Redis with TTL.

    Workers call this once per task and read attributes off the result
    instead of using hardcoded constants.
    """
    org_id_str = str(org_id)
    cache_key = _cache_key(org_id_str)

    # Try cache first
    try:
        cached = _redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return OrgConfig(**data)
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}. Falling back to DB.")

    # Cache miss or Redis error — read from DB
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = db.query(DetectionConfig).filter_by(org_id=org_id_str).first()
        if row is None:
            logger.warning(
                f"No detection_config row for org_id={org_id_str}. "
                f"Using built-in defaults. Run scripts.seed_org to populate."
            )
            cfg = OrgConfig.from_defaults(org_id_str)
        else:
            cfg = OrgConfig.from_db_row(org_id_str, row)

        # Write-through to cache
        try:
            _redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(asdict(cfg)))
        except Exception as e:
            logger.warning(f"Redis write failed for {cache_key}: {e}. Continuing.")

        return cfg
    finally:
        if own_session:
            db.close()


def invalidate_org_config(org_id: Union[str, UUID]) -> None:
    """
    Call after any admin edit to detection_config so the next worker
    sees the new values immediately rather than waiting for TTL.
    """
    try:
        _redis.delete(_cache_key(str(org_id)))
        logger.info(f"Invalidated config cache for org {org_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate cache for org {org_id}: {e}")


# =====================================================
# Convenience: resolve org by slug (for tests / scripts)
# =====================================================
def get_org_id_by_slug(slug: str, db: Optional[Session] = None) -> Optional[str]:
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = db.query(Organization).filter_by(slug=slug).first()
        return str(row.id) if row else None
    finally:
        if own_session:
            db.close()