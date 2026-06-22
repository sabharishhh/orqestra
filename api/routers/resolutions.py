from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from core.database import get_db
from models.database import Resolution

# This is the line FastAPI was looking for!
router = APIRouter()

@router.get("/{contradiction_id}")
def get_resolution_for_contradiction(contradiction_id: UUID, db: Session = Depends(get_db)):
    """Fetches the AI-generated resolution proposal for a specific contradiction."""
    resolution = db.query(Resolution).filter(Resolution.contradiction_id == contradiction_id).first()
    
    if not resolution:
        raise HTTPException(status_code=404, detail="Resolution not yet generated or contradiction ID invalid.")
        
    return {
        "id": resolution.id,
        "contradiction_id": resolution.contradiction_id,
        "why_they_contradict": resolution.why_they_contradict,
        "likely_stale_system": resolution.likely_stale_system,
        "risk_reason": resolution.risk_reason,
        "recommended_action": resolution.recommended_action,
        "target_uri": resolution.target_uri,
        "estimated_cost": resolution.estimated_cost,
        "generated_at": resolution.generated_at
    }