from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from core.database import get_db
from models.database import Contradiction, Claim, System

router = APIRouter()

@router.get("/")
def get_active_contradictions(status: str = "open", limit: int = 50, db: Session = Depends(get_db)):
    """Returns the live feed of semantic collisions across the estate."""
    results = []
    
    # Query contradictions and join to fetch the actual claim texts and system names
    contradictions = db.query(Contradiction).filter(Contradiction.status == status)\
                       .order_by(desc(Contradiction.detected_at)).limit(limit).all()
                       
    for c in contradictions:
        claim_a = db.query(Claim).filter(Claim.id == c.claim_a_id).first()
        claim_b = db.query(Claim).filter(Claim.id == c.claim_b_id).first()
        
        if not claim_a or not claim_b:
            continue
            
        sys_a = db.query(System).filter(System.id == claim_a.system_id).first()
        sys_b = db.query(System).filter(System.id == claim_b.system_id).first()
        
        results.append({
            "id": c.id,
            "severity": c.severity,
            "entity_hint": claim_a.entity_hint,
            "nli_score": c.nli_score,
            "detected_at": c.detected_at,
            "system_a": {
                "name": sys_a.name if sys_a else "Unknown",
                "claim": f"{claim_a.subject} {claim_a.predicate} {claim_a.object}"
            },
            "system_b": {
                "name": sys_b.name if sys_b else "Unknown",
                "claim": f"{claim_b.subject} {claim_b.predicate} {claim_b.object}"
            }
        })
        
    return results