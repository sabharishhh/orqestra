from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID

from core.database import get_db
from models.database import System
from api.auth import verify_api_key

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