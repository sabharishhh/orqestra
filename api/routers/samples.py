from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Dict, Any, Optional

from core.database import get_db
from models.database import System
from api.auth import verify_api_key

# We will build this Celery task in the next step
from workers.tasks import process_sample_task 

router = APIRouter()

# --- Pydantic Schemas ---
class SamplePayload(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None
    vector_clock: Optional[Dict[str, Any]] = None

class BatchSamplePayload(BaseModel):
    samples: List[SamplePayload]

# --- Endpoints ---
@router.post("/{system_id}/samples", status_code=202, dependencies=[Depends(verify_api_key)])
async def ingest_sample(system_id: UUID, payload: SamplePayload, db: Session = Depends(get_db)):
    """
    Standard ingestion. Accepts raw agent text and immediately dispatches 
    to the asynchronous claim extraction worker queue.
    """
    # Verify system exists before queueing
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")

    # Fire and forget to Celery Queue
    process_sample_task.delay(str(system_id), payload.text, payload.metadata)
    
    return {"status": "queued", "message": "Sample accepted for SCCG extraction."}


@router.post("/{system_id}/samples/batch", status_code=202, dependencies=[Depends(verify_api_key)])
async def ingest_batch_samples(system_id: UUID, payload: BatchSamplePayload, db: Session = Depends(get_db)):
    """High-throughput batch ingestion for log replays."""
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")

    for sample in payload.samples:
        process_sample_task.delay(str(system_id), sample.text, sample.metadata)
        
    return {"status": "queued", "count": len(payload.samples)}


@router.post("/{system_id}/write-hook", status_code=202, dependencies=[Depends(verify_api_key)])
async def agent_write_hook(system_id: UUID, payload: SamplePayload, db: Session = Depends(get_db)):
    """
    Specialized drop-in endpoint for Orqestra SDK Wrappers. 
    Functionally identical to /samples but tags metadata for Hook-origin tracing.
    """
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")

    # FIX: Safety wrapper for when payload.metadata is None
    meta = dict(payload.metadata or {})
    meta["origin"] = "sdk_write_hook"
    
    process_sample_task.delay(str(system_id), payload.text, meta)
    
    return {"status": "hook_queued"}