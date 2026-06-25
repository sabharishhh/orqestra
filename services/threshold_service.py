"""
Per-organization per-category threshold resolution.

Each canonical entity declares a `category` (e.g. 'consumer', 'clinical',
'compliance'). Each category has its own cosine threshold profile in the
`category_thresholds` table:
  - level_0_cosine: OBG centroid divergence threshold
  - level_3_cosine: HNSW neighbor distance threshold for cross-system pairing
  - nli_floor:      Level 4 NLI confidence floor (nullable; falls back to
                    DetectionConfig.nli_confidence_floor when null)

This is the single point where "how loose is the funnel for this entity"
is computed across the codebase. Sprint 3.1 wires it into Levels 0, 3,
and 4 of contradiction_detector.py, replacing the hardcoded constants.

Cached aggressively because the detector calls this on every claim.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import CanonicalEntity, CategoryThreshold
from services.config_loader import get_org_config, _redis, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)


# =====================================================
# Fallback defaults
# Applied when the org has no category_thresholds row for a category,
# OR when the canonical entity is unknown (falls into the 'general' bucket).
# Numerically match the legacy hardcoded values for safety.
# =====================================================
DEFAULT_THRESHOLDS = {
    "general":    {"level_0_cosine": 0.35, "level_3_cosine": 0.40, "nli_floor": None},
    "consumer":   {"level_0_cosine": 0.40, "level_3_cosine": 0.45, "nli_floor": None},
    "clinical":   {"level_0_cosine": 0.25, "level_3_cosine": 0.30, "nli_floor": 0.60},
    "compliance": {"level_0_cosine": 0.25, "level_3_cosine": 0.30, "nli_floor": 0.65},
    "pricing":    {"level_0_cosine": 0.30, "level_3_cosine": 0.35, "nli_floor": None},
    "policy":     {"level_0_cosine": 0.35, "level_3_cosine": 0.40, "nli_floor": None},
}


@dataclass
class ThresholdProfile:
    org_id: str
    category: str
    level_0_cosine: float    # OBG centroid divergence threshold (Level 0)
    level_3_cosine: float    # HNSW cross-system neighbor threshold (Level 3)
    nli_floor: float         # Level 4 NLI confidence floor (resolved, not nullable)


def _category_cache_key(org_id: str, category: str) -> str:
    return f"orqestra:threshold:{org_id}:{category}"


def _entity_category_cache_key(org_id: str, canonical_name: str) -> str:
    return f"orqestra:entcategory:{org_id}:{canonical_name}"


def _resolve_category(org_id: str, canonical_name: str, db: Session) -> str:
    """Look up CanonicalEntity.category. Cached. Returns 'general' if unknown."""
    cache_key = _entity_category_cache_key(org_id, canonical_name)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return cached
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    row = (db.query(CanonicalEntity.category)
             .filter_by(org_id=org_id, canonical_name=canonical_name)
             .first())
    category = row.category if row else "general"

    try:
        _redis.setex(cache_key, CACHE_TTL_SECONDS, category)
    except Exception as e:
        logger.warning(f"Redis write failed for {cache_key}: {e}")

    return category


def _load_thresholds_for_category(org_id: str, category: str, db: Session) -> dict:
    """Returns {level_0_cosine, level_3_cosine, nli_floor}. Cached."""
    cache_key = _category_cache_key(org_id, category)
    try:
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis read failed for {cache_key}: {e}")

    row = (db.query(CategoryThreshold)
             .filter_by(org_id=org_id, category=category)
             .first())

    if row is None:
        # No DB row — fall back to hardcoded defaults for this category,
        # or 'general' if we don't even have defaults for it.
        fallback = DEFAULT_THRESHOLDS.get(category, DEFAULT_THRESHOLDS["general"])
        logger.warning(
            f"No category_thresholds row for org={org_id} category='{category}'. "
            f"Using built-in default: {fallback}"
        )
        result = dict(fallback)
    else:
        result = {
            "level_0_cosine": row.level_0_cosine,
            "level_3_cosine": row.level_3_cosine,
            "nli_floor":      row.nli_floor,
        }

    try:
        _redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
    except Exception as e:
        logger.warning(f"Redis write failed for {cache_key}: {e}")

    return result


def get_thresholds_for_entity(
    org_id: Union[str, UUID],
    canonical_entity: str,
    db: Optional[Session] = None,
) -> ThresholdProfile:
    """
    Resolve the funnel thresholds for a specific canonical entity.

    Routing:
        canonical_entity → CanonicalEntity.category → CategoryThreshold row
        (or DEFAULT_THRESHOLDS[category] if no row).
        nli_floor resolves to DetectionConfig.nli_confidence_floor when null.

    Args:
        org_id: tenant scope
        canonical_entity: post-resolution canonical name (e.g. 'workout_routine')
        db: optional session — if provided, skips opening one
    """
    org_id_str = str(org_id)
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        category = _resolve_category(org_id_str, canonical_entity, db)
        raw = _load_thresholds_for_category(org_id_str, category, db)

        # Resolve nullable nli_floor against org default
        nli_floor = raw["nli_floor"]
        if nli_floor is None:
            cfg = get_org_config(org_id_str, db)
            nli_floor = cfg.nli_confidence_floor

        return ThresholdProfile(
            org_id=org_id_str,
            category=category,
            level_0_cosine=raw["level_0_cosine"],
            level_3_cosine=raw["level_3_cosine"],
            nli_floor=nli_floor,
        )
    finally:
        if own_session:
            db.close()


def invalidate_thresholds(org_id: Union[str, UUID], category: Optional[str] = None) -> None:
    """Drop cached thresholds for a category, or all categories for the org."""
    try:
        if category:
            _redis.delete(_category_cache_key(str(org_id), category))
        else:
            pattern = f"orqestra:threshold:{org_id}:*"
            for key in _redis.scan_iter(match=pattern):
                _redis.delete(key)
            # Also invalidate entity→category mappings
            ent_pattern = f"orqestra:entcategory:{org_id}:*"
            for key in _redis.scan_iter(match=ent_pattern):
                _redis.delete(key)
        logger.info(f"Invalidated threshold cache for org={org_id} category={category or 'ALL'}")
    except Exception as e:
        logger.warning(f"Failed to invalidate threshold cache: {e}")