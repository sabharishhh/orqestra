from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.database import get_db
from models.database import Contradiction, System
from api.auth import verify_api_key

router = APIRouter()


@router.get("/summary")
def get_roi_summary(
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Aggregates the caller's org's total business risk.

    Sprint 8 Task 4: previously returned global aggregates across every
    org's contradictions. Now org-scoped via verify_api_key.
    """
    org_id = system.org_id
    open_filter = (
        (Contradiction.status == "open") & (Contradiction.org_id == org_id)
    )

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