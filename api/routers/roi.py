from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from models.database import Contradiction, ResolutionProposal

router = APIRouter()

@router.get("/summary")
def get_roi_summary(db: Session = Depends(get_db)):
    """Aggregates the total business risk captured by the Orqestra platform."""
    
    # Get counts by severity
    critical_count = db.query(Contradiction).filter_by(severity="critical", status="open").count()
    high_count = db.query(Contradiction).filter_by(severity="high", status="open").count()
    medium_count = db.query(Contradiction).filter_by(severity="medium", status="open").count()
    
    # Simple deterministic cost aggregation based on our Consumer thresholds
    # High = $1200 (LTV Loss), Medium = $150 (Support Ticket)
    total_liability = (high_count * 1200) + (medium_count * 150)
    
    return {
        "active_contradictions": critical_count + high_count + medium_count,
        "severity_breakdown": {
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": db.query(Contradiction).filter_by(severity="low", status="open").count()
        },
        "total_financial_exposure_usd": total_liability,
        "platform_roi_status": "positive" if total_liability > 0 else "neutral"
    }