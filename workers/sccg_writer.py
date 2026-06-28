import logging
from observability import get_logger
from typing import List, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import Claim, System
from services.content_hasher import normalize_and_hash
from services.entity_resolver import resolve_entity_hint

logger = get_logger(__name__)


def _resolve_org_id(db: Session, system_id: str) -> str:
    """Look up org_id for a system. One DB hit per write_claims_to_sccg call."""
    row = db.query(System.org_id).filter(System.id == system_id).first()
    if row is None:
        raise RuntimeError(f"System {system_id} has no org_id — Sprint 1.3 backfill missing?")
    return str(row.org_id)


def _load_external_parent(
    db: Session,
    parent_claim_id: Optional[str],
    expected_org_id: str,
) -> Optional[Claim]:
    """
    Sprint 6.5: load the externally-declared parent claim (potentially from
    another agent in the same org). Returns None if not provided. Raises if
    the parent doesn't exist or crosses tenant boundaries (defense-in-depth;
    the API also validates this).
    """
    if not parent_claim_id:
        return None

    parent = db.query(Claim).filter(Claim.id == parent_claim_id).first()
    if parent is None:
        logger.warning(
            f"SCCG Writer: parent_claim_id {parent_claim_id} not found. "
            f"Falling back to same-system inference."
        )
        return None
    if str(parent.org_id) != expected_org_id:
        logger.error(
            f"SCCG Writer: parent_claim_id {parent_claim_id} crosses tenant boundary "
            f"(parent org={parent.org_id}, expected={expected_org_id}). REJECTING."
        )
        return None
    return parent


def write_claims_to_sccg(
    system_id: str,
    embedded_claims_data: List[Dict],
    parent_claim_id: Optional[str] = None,
) -> List[str]:
    """
    Writes deeply extracted claims into the SCCG Postgres table.
    Enforces F8.4 Append-Only Guardrails, Level 2 Deduplication,
    calculates Dynamic Vector Clocks, and maintains strict Merkle ancestry.

    Sprint 6.5: parent_claim_id is an optional cross-agent parent pointer.
    When provided, the FIRST claim in this batch is linked to it (potentially
    pointing to another agent's claim). Subsequent claims in the same batch
    chain naturally from the previous claim in the batch, preserving the
    same-system DAG. This enables cross-agent lineage and real LCAs.
    """
    if not embedded_claims_data:
        return []

    inserted_ids = []
    db: Session = SessionLocal()

    try:
        org_id = _resolve_org_id(db, system_id)

        # Sprint 6.5: load the external parent (if any). This will be used
        # as the parent for the FIRST claim in the batch, overriding the
        # default same-system temporal inference.
        external_parent = _load_external_parent(db, parent_claim_id, org_id)

        # Track the "most recent claim in this batch" so subsequent claims
        # chain through it. Seeded with the external parent if provided,
        # otherwise None (writer falls back to same-system temporal lookup).
        batch_parent_override: Optional[Claim] = external_parent

        for claim_index, data in enumerate(embedded_claims_data):
            subject = data["claim"]["subject"]
            predicate = data["claim"]["predicate"]
            obj = data["claim"].get("object", data["claim"].get("obj", ""))
            context = data["claim"]["context"]

            raw_hint = data["claim"].get("entity_hint", "general")
            entity_hint = resolve_entity_hint(
                org_id,
                raw_hint,
                embedding=data["embedding"],
                db=db,
            )

            content_hash = normalize_and_hash(subject, predicate, obj)

            # Deduplication
            is_duplicate = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.content_hash == content_hash
            ).first()

            if is_duplicate:
                logger.info(
                    f"Level 2 Funnel: Dropping duplicate claim. "
                    f"Hash [{content_hash[:8]}] already exists for System."
                )
                continue

            # =====================================================
            # PARENT DETERMINATION (Sprint 6.5 hierarchy):
            #   1. If batch_parent_override is set (external parent OR
            #      previous claim in this same batch), use it.
            #   2. Otherwise, fall back to same-system temporal inference.
            # =====================================================
            if batch_parent_override is not None:
                previous_claim = batch_parent_override
            else:
                previous_claim = db.query(Claim).filter(
                    Claim.system_id == system_id,
                    Claim.entity_hint == entity_hint
                ).order_by(Claim.extracted_at.desc()).first()

            # Vector clock: inherit from previous_claim's clock (which may
            # belong to a different system if external_parent is in use)
            new_clock = (
                previous_claim.vector_clock.copy()
                if previous_claim and previous_claim.vector_clock
                else {}
            )

            sys_key = str(system_id)
            logical_tick = new_clock.get(sys_key, 0) + 1
            new_clock[sys_key] = logical_tick

            # F2.4 / ISSUE-05: True DAG ancestry
            parent_id_for_claim = previous_claim.id if previous_claim else None
            parent_hashes = (
                [previous_claim.content_hash]
                if previous_claim and previous_claim.content_hash
                else []
            )

            new_claim = Claim(
                org_id=org_id,
                system_id=system_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                context=context,
                entity_hint=entity_hint,
                embedding=data["embedding"],
                vector_clock=new_clock,
                content_hash=content_hash,
                parent_claim_id=parent_id_for_claim,
                parent_hashes=parent_hashes,
                logical_clock=logical_tick,
                is_historical=False,
            )
            db.add(new_claim)
            db.flush()
            inserted_ids.append(str(new_claim.id))

            # The next claim in this batch should chain from THIS claim,
            # not the external parent (which only applies to the first).
            batch_parent_override = new_claim

        db.commit()

        if inserted_ids:
            cross_agent_note = (
                f", first claim linked to external parent {parent_claim_id}"
                if external_parent else ""
            )
            logger.info(
                f"SCCG Writer: Committed {len(inserted_ids)} new claims "
                f"for System [{system_id}] (org={org_id}){cross_agent_note}"
            )
        else:
            logger.info(
                f"SCCG Writer: 0 new claims committed for System [{system_id}] "
                f"(All duplicates dropped)"
            )

        return inserted_ids

    except Exception as e:
        db.rollback()
        logger.error(f"Critical SCCG Write Failure: {e}")
        raise
    finally:
        db.close()