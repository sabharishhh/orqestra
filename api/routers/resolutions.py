from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from core.database import get_db
from models.database import ResolutionProposal
from pydantic import BaseModel

router = APIRouter()

class FeedbackRequest(BaseModel):
    action: str 

@router.get("/pending")
def get_pending_resolutions(db: Session = Depends(get_db)):
    return db.query(ResolutionProposal).filter(ResolutionProposal.status == "pending").limit(5).all()

@router.get("/{contradiction_id}")
def get_resolution_for_contradiction(contradiction_id: UUID, db: Session = Depends(get_db)):
    resolution = db.query(ResolutionProposal).filter(ResolutionProposal.contradiction_id == contradiction_id).first()
    
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

@router.post("/{id}/feedback")
def submit_feedback(id: str, payload: FeedbackRequest, db: Session = Depends(get_db)):
    res = db.query(ResolutionProposal).filter_by(id=id).first()
    if not res:
        raise HTTPException(status_code=404, detail="Resolution not found.")
        
    res.status = payload.action

    if payload.action == "accept":
        from models.database import Contradiction
        contradiction = db.query(Contradiction).filter_by(id=res.contradiction_id).first()
        if contradiction:
            contradiction.status = "resolved"

    db.commit()
    
    from workers.feedback_collector import record_feedback
    record_feedback.delay(id, payload.action)
    
    return {"status": "feedback_logged", "action": payload.action}