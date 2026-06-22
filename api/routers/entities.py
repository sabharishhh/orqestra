from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from core.database import get_db
from models.database import EntityBeliefState, System

router = APIRouter()

@router.get("/unstable")
def get_unstable_entities(limit: int = 10, db: Session = Depends(get_db)):
    """
    Returns entities that have the highest sample counts across multiple systems,
    indicating heavy cross-agent debate or frequent updates.
    """
    results = []
    
    # Simple proxy for instability: Entities that get updated the most
    entities = db.query(EntityBeliefState).order_by(desc(EntityBeliefState.sample_count)).limit(limit).all()
    
    for e in entities:
        sys = db.query(System).filter(System.id == e.system_id).first()
        results.append({
            "entity_name": e.entity_name,
            "system_name": sys.name if sys else "Unknown",
            "updates": e.sample_count,
            "last_updated": e.last_updated_at
        })
        
    return results