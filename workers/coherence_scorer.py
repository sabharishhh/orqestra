import math
import logging
from observability import get_logger
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.celery_app import celery_app
from models.database import (
    Contradiction,
    CoherenceScore,
    Claim,
    System,
    CanonicalEntity,
)
from services.config_loader import get_org_config

logger = get_logger(__name__)


def _resolve_org_id(db: Session, system_id: str) -> str:
    row = db.query(System.org_id).filter(System.id == system_id).first()
    if row is None:
        raise RuntimeError(f"System {system_id} has no org_id — Sprint 1.3 backfill missing?")
    return str(row.org_id)


def _load_entity_importance(db: Session, org_id: str, entity_hint: str, default: float = 0.5) -> float:
    """Per-org importance from canonical_entities. Falls back to 0.5 for orphans."""
    if not entity_hint:
        return default
    row = (
        db.query(CanonicalEntity.importance)
          .filter_by(org_id=org_id, canonical_name=entity_hint)
          .first()
    )
    if row is None or row.importance is None:
        return default
    return float(row.importance)


@celery_app.task(queue="claim_extraction")
def update_coherence_score(system_id: str):
    """
    Worker 6: Calculates exponential time-decay coherence score (multi-tenant).

    All tuning parameters now read from per-org config:
      - window_days: DetectionConfig.coherence_window_days
      - importance:  CanonicalEntity.importance (per-entity, per-org)
      - decay rate:  DetectionConfig.recency_decay_lambda
    """
    db: Session = SessionLocal()
    try:
        org_id = _resolve_org_id(db, system_id)
        cfg = get_org_config(org_id, db)

        window_days = cfg.coherence_window_days
        decay_lambda = cfg.recency_decay_lambda

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=window_days)

        active_contradictions = (
            db.query(Contradiction)
              .join(Claim, Contradiction.claim_a_id == Claim.id)
              .filter(
                  Claim.system_id == system_id,
                  Contradiction.status == 'open',
                  Contradiction.detected_at >= cutoff,
              )
              .all()
        )

        if not active_contradictions:
            _upsert_score(db, org_id, system_id, 1.0, 0, Counter(), window_days)
            return

        numerator = 0.0
        denominator = 0.0
        for c in active_contradictions:
            claim_a = db.query(Claim.entity_hint).filter_by(id=c.claim_a_id).first()
            entity_hint = claim_a.entity_hint if claim_a else None
            importance = _load_entity_importance(db, org_id, entity_hint)

            days_old = max(0, (now - c.detected_at).days)
            recency = math.exp(-decay_lambda * days_old)
            weight = importance * recency

            numerator += c.nli_score * weight
            denominator += weight

        raw_score = 1.0 - (numerator / denominator) if denominator > 0 else 1.0
        final_score = max(0.0, min(1.0, raw_score))

        severity_counts = Counter(c.severity for c in active_contradictions)
        _upsert_score(db, org_id, system_id, final_score, len(active_contradictions), severity_counts, window_days)

        logger.info(
            f"Updated Coherence Score for System [{system_id}] (org={org_id}): "
            f"{final_score:.4f} (window={window_days}d, decay={decay_lambda})"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Coherence scorer failed: {e}")
    finally:
        db.close()


def _upsert_score(db: Session, org_id: str, system_id: str, score: float, total_active: int,
                  severity_counts: Counter, window_days: int):
    """Helper to cleanly upsert the calculated score."""
    existing = db.query(CoherenceScore).filter_by(system_id=system_id).first()
    if existing:
        existing.org_id = org_id   # Defensive — re-assert in case of legacy nulls
        existing.score = score
        existing.active_contradictions = total_active
        existing.critical_count = severity_counts.get("critical", 0)
        existing.high_count = severity_counts.get("high", 0)
        existing.medium_count = severity_counts.get("medium", 0)
        existing.low_count = severity_counts.get("low", 0)
        existing.computed_at = datetime.now(timezone.utc)
    else:
        new_score = CoherenceScore(
            org_id=org_id,         # ← Sprint 3.6a: tenant scope
            system_id=system_id,
            score=score,
            active_contradictions=total_active,
            critical_count=severity_counts.get("critical", 0),
            high_count=severity_counts.get("high", 0),
            medium_count=severity_counts.get("medium", 0),
            low_count=severity_counts.get("low", 0),
            window_days=window_days,
        )
        db.add(new_score)
    db.commit()