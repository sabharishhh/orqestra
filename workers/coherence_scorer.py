import math
import logging
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Contradiction, CoherenceScore, Entity
from core.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(queue="claim_extraction")
def update_coherence_score(system_id: str, window_days: int = 30):
    """Worker 6: Calculates exponential time-decay coherence score."""
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        # Contradictions don't store system_id directly — must join through claims
        from models.database import Claim as ClaimModel
        active_contradictions = db.query(Contradiction).join(
            ClaimModel, Contradiction.claim_a_id == ClaimModel.id
        ).filter(
            ClaimModel.system_id == system_id,
            Contradiction.status == 'open',
            Contradiction.detected_at >= cutoff
        ).all()

        if not active_contradictions:
            _upsert_score(db, system_id, 1.0, 0, Counter(), window_days)
            return

        numerator = 0.0
        denominator = 0.0

        for c in active_contradictions:
            entity = db.query(Entity).filter_by(id=c.entity_id).first() if c.entity_id else None
            importance = entity.importance if entity else 0.5
            
            # Recency Weight: exp(-0.05 * days_since_detection)
            days_old = (datetime.utcnow() - c.detected_at).days
            recency = math.exp(-0.05 * days_old)
            
            weight = importance * recency
            numerator += c.nli_score * weight
            denominator += weight

        # Final Coherence Calculation
        raw_score = 1.0 - (numerator / denominator) if denominator > 0 else 1.0
        final_score = max(0.0, min(1.0, raw_score))
        
        severity_counts = Counter(c.severity for c in active_contradictions)
        _upsert_score(db, system_id, final_score, len(active_contradictions), severity_counts, window_days)

        logger.info(f"Updated Coherence Score for System [{system_id}]: {final_score:.4f}")

    except Exception as e:
        db.rollback()
        logger.error(f"Coherence scorer failed: {e}")
    finally:
        db.close()

def _upsert_score(db: Session, system_id: str, score: float, total_active: int, severity_counts: Counter, window_days: int):
    """Helper to cleanly upsert the calculated score."""
    existing = db.query(CoherenceScore).filter_by(system_id=system_id).first()
    if existing:
        existing.score = score
        existing.active_contradictions = total_active
        existing.critical_count = severity_counts.get("critical", 0)
        existing.high_count = severity_counts.get("high", 0)
        existing.medium_count = severity_counts.get("medium", 0)
        existing.low_count = severity_counts.get("low", 0)
        existing.computed_at = datetime.utcnow()
    else:
        new_score = CoherenceScore(
            system_id=system_id,
            score=score,
            active_contradictions=total_active,
            critical_count=severity_counts.get("critical", 0),
            high_count=severity_counts.get("high", 0),
            medium_count=severity_counts.get("medium", 0),
            low_count=severity_counts.get("low", 0),
            window_days=window_days
        )
        db.add(new_score)
    db.commit()