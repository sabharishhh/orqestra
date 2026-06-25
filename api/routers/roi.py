from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from models.database import Contradiction

router = APIRouter()


@router.get("/summary")
def get_roi_summary(db: Session = Depends(get_db)):
    """
    Aggregates the total business risk captured by the Orqestra platform.

    Sprint 3.5: cost is now persisted per-contradiction by the detector
    (Sprint 3.1) via services.severity_scorer, which reads per-entity
    cost_high_usd / cost_critical_usd from the canonical_entities table.
    No hardcoded multipliers — the dashboard number reflects whatever the
    org has configured.
    """
    open_filter = (Contradiction.status == "open")

    # Severity breakdown — single grouped query instead of four separate counts
    severity_rows = (
        db.query(Contradiction.severity, func.count(Contradiction.id))
          .filter(open_filter)
          .group_by(Contradiction.severity)
          .all()
    )
    severity_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for sev, count in severity_rows:
        if sev in severity_breakdown:
            severity_breakdown[sev] = count

    active_total = sum(severity_breakdown.values())

    # Real cost aggregation from per-contradiction cost_usd
    total_liability = (
        db.query(func.coalesce(func.sum(Contradiction.cost_usd), 0))
          .filter(open_filter)
          .scalar()
    )

    return {
        "active_contradictions": active_total,
        "severity_breakdown": severity_breakdown,
        "total_financial_exposure_usd": int(total_liability),
        "platform_roi_status": "positive" if total_liability > 0 else "neutral",
    }