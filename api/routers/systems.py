from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID

from core.database import get_db
from models.database import System
from api.auth import verify_api_key
from models.database import CoherenceScore


router = APIRouter()

# --- Pydantic Schemas ---
class SystemCreate(BaseModel):
    name: str
    provider: str = "openai"
    description: str | None = None

class SystemResponse(SystemCreate):
    id: UUID

# --- Endpoints ---
@router.post("/", response_model=SystemResponse, dependencies=[Depends(verify_api_key)])
async def register_system(system: SystemCreate, db: Session = Depends(get_db)):
    """Registers a new AI Agent to the Estate monitoring index."""
    existing = db.query(System).filter(System.name == system.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="System name already registered.")
        
    new_system = System(
        name=system.name,
        provider=system.provider,
        description=system.description
    )
    db.add(new_system)
    db.commit()
    db.refresh(new_system)
    return new_system

@router.get("/", response_model=list[SystemResponse])
async def list_systems(db: Session = Depends(get_db)):
    """Returns all tracked AI agents in the estate."""
    return db.query(System).all()

@router.get("/{system_id}/score")
def get_system_coherence(system_id: UUID, db: Session = Depends(get_db)):
    score = db.query(CoherenceScore).filter_by(system_id=str(system_id)).first()
    if not score: raise HTTPException(404, "No coherence score computed yet.")
    return {
        "system_id": str(score.system_id),
        "score": score.score,
        "active_contradictions": score.active_contradictions,
        "severity_breakdown": {
            "critical": score.critical_count,
            "high": score.high_count,
            "medium": score.medium_count,
            "low": score.low_count,
        },
        "window_days": score.window_days,
        "computed_at": score.computed_at,
    }

@router.get("/estate/score")
def get_estate_coherence(db: Session = Depends(get_db)):
    """Estate-level: weighted mean of per-system scores."""
    scores = db.query(CoherenceScore).all()
    if not scores: return {"estate_score": 1.0, "system_count": 0}
    total_active = sum(s.active_contradictions for s in scores)
    weighted = sum(s.score * (1 + s.active_contradictions) for s in scores)
    weights = sum(1 + s.active_contradictions for s in scores)
    return {
        "estate_score": round(weighted / weights, 4) if weights else 1.0,
        "system_count": len(scores),
        "total_active_contradictions": total_active,
    }