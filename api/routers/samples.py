from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Dict, Any, Optional

from core.database import get_db
from models.database import System, Claim
from api.auth import verify_api_key, verify_write_hook_signature
from workers.tasks import process_sample_task

router = APIRouter()


# --- Pydantic Schemas ---
class SamplePayload(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None
    vector_clock: Optional[Dict[str, Any]] = None
    # Sprint 6.5: Optional cross-agent parent pointer. When provided, the
    # first claim extracted from this sample will be linked to parent_claim_id
    # in the SCCG, enabling cross-agent lineage (Lowest Common Ancestor
    # detection across agents that share derived context).
    parent_claim_id: Optional[UUID] = None


class BatchSamplePayload(BaseModel):
    samples: List[SamplePayload]


# --- Helpers ---
def _validate_parent_claim(
    db: Session,
    parent_claim_id: Optional[UUID],
    caller_system: System,
) -> None:
    """
    Sprint 6.5 tenant boundary check.

    If the caller declares a parent_claim_id, ensure:
      1. The parent claim actually exists in the DB
      2. The parent claim belongs to the same org as the calling system

    Cross-tenant parent pointers are rejected with 400 — they would
    leak the existence of another tenant's claim IDs and corrupt the
    SCCG's tenant isolation guarantees.
    """
    if parent_claim_id is None:
        return

    parent = db.query(Claim.org_id).filter(Claim.id == parent_claim_id).first()
    if parent is None:
        raise HTTPException(
            status_code=400,
            detail=f"parent_claim_id {parent_claim_id} does not exist.",
        )
    if str(parent.org_id) != str(caller_system.org_id):
        # Note: return 400 not 403, so we don't leak existence vs permission.
        raise HTTPException(
            status_code=400,
            detail=f"parent_claim_id {parent_claim_id} is not accessible to your organization.",
        )


# --- Endpoints ---
@router.post("/{system_id}/samples", status_code=202)
async def ingest_sample(
    system_id: UUID,
    payload: SamplePayload,
    db: Session = Depends(get_db),
    caller_system: System = Depends(verify_api_key),
):
    """
    Standard ingestion. Accepts raw agent text and immediately dispatches
    to the asynchronous claim extraction worker queue.

    Sprint 6.5: optionally accepts parent_claim_id so the agent can declare
    "this sample's first claim is derived from this prior claim". Used for
    cross-agent lineage when one agent's output feeds another's input.
    """
    # Verify system exists and belongs to caller's org
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")
    if str(system.org_id) != str(caller_system.org_id):
        raise HTTPException(status_code=404, detail="System ID not found.")

    # Validate parent_claim_id (tenant-scoped existence check)
    _validate_parent_claim(db, payload.parent_claim_id, caller_system)

    process_sample_task.delay(
        str(system_id),
        payload.text,
        payload.metadata,
        str(payload.parent_claim_id) if payload.parent_claim_id else None,
    )
    return {"status": "queued", "message": "Sample accepted for SCCG extraction."}


@router.post("/{system_id}/samples/batch", status_code=202)
async def ingest_batch_samples(
    system_id: UUID,
    payload: BatchSamplePayload,
    db: Session = Depends(get_db),
    caller_system: System = Depends(verify_api_key),
):
    """High-throughput batch ingestion for log replays. Each sample may
    independently declare its own parent_claim_id."""
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")
    if str(system.org_id) != str(caller_system.org_id):
        raise HTTPException(status_code=404, detail="System ID not found.")

    # Validate every parent_claim_id in the batch before queueing anything
    for sample in payload.samples:
        _validate_parent_claim(db, sample.parent_claim_id, caller_system)

    for sample in payload.samples:
        process_sample_task.delay(
            str(system_id),
            sample.text,
            sample.metadata,
            str(sample.parent_claim_id) if sample.parent_claim_id else None,
        )
    return {"status": "queued", "count": len(payload.samples)}


@router.post("/{system_id}/write-hook", status_code=202)
async def agent_write_hook(
    system_id: UUID,
    payload: SamplePayload,
    db: Session = Depends(get_db),
    caller_system: System = Depends(verify_write_hook_signature),
):
    """
    Specialized drop-in endpoint for Orqestra SDK Wrappers.
    Functionally identical to /samples but tags metadata for Hook-origin tracing.
    Sprint 6.5: also supports parent_claim_id for SDK-driven causal chaining.
    """
    system = db.query(System).filter(System.id == system_id).first()
    if not system:
        raise HTTPException(status_code=404, detail="System ID not found.")
    if str(system.org_id) != str(caller_system.org_id):
        raise HTTPException(status_code=404, detail="System ID not found.")

    _validate_parent_claim(db, payload.parent_claim_id, caller_system)

    meta = dict(payload.metadata or {})
    meta["origin"] = "sdk_write_hook"

    process_sample_task.delay(
        str(system_id),
        payload.text,
        meta,
        str(payload.parent_claim_id) if payload.parent_claim_id else None,
    )
    return {"status": "hook_queued"}