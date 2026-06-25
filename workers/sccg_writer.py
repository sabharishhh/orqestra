import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim, System
from services.content_hasher import normalize_and_hash  # F1.2 / ISSUE-15 FIX
from services.entity_resolver import resolve_entity_hint

logger = logging.getLogger(__name__)


def _resolve_org_id(db: Session, system_id: str) -> str:
    """Look up org_id for a system. One DB hit per write_claims_to_sccg call."""
    row = db.query(System.org_id).filter(System.id == system_id).first()
    if row is None:
        raise RuntimeError(f"System {system_id} has no org_id — Sprint 1.3 backfill missing?")
    return str(row.org_id)


def write_claims_to_sccg(system_id: str, embedded_claims_data: List[Dict]) -> List[str]:
    """
    Writes deeply extracted claims into the SCCG Postgres table.
    Enforces F8.4 Append-Only Guardrails, Level 2 Deduplication,
    calculates Dynamic Vector Clocks, and maintains strict Merkle ancestry.

    Sprint 3.2: tenant-scoped via org_id resolved from the system's
    organizations FK. Entity hints canonicalize against the org's
    canonical_entities table.
    """
    if not embedded_claims_data:
        return []

    inserted_ids = []
    db: Session = SessionLocal()

    try:
        # Resolve org_id once per batch — all claims in this batch share it
        org_id = _resolve_org_id(db, system_id)

        for data in embedded_claims_data:
            subject = data["claim"]["subject"]
            predicate = data["claim"]["predicate"]
            obj = data["claim"].get("object", data["claim"].get("obj", ""))
            context = data["claim"]["context"]

            # --- ISSUE-03 FIX: Entity Hint Normalization (org-scoped) ---
            raw_hint = data["claim"].get("entity_hint", "general")
            entity_hint = resolve_entity_hint(
                org_id,
                raw_hint,
                embedding=data["embedding"],
                db=db,
            )

            # --- LEVEL 2: CONTENT HASHING (ISSUE-15 & ISSUE-05 FIX) ---
            content_hash = normalize_and_hash(subject, predicate, obj)

            # Deduplication uses the dedicated content_hash column
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

            # --- DYNAMIC VECTOR CLOCK & ANCESTRY MATH ---
            previous_claim = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.entity_hint == entity_hint
            ).order_by(Claim.extracted_at.desc()).first()

            new_clock = (
                previous_claim.vector_clock.copy()
                if previous_claim and previous_claim.vector_clock
                else {}
            )

            sys_key = str(system_id)
            logical_tick = new_clock.get(sys_key, 0) + 1
            new_clock[sys_key] = logical_tick

            # F2.4 / ISSUE-05 Fix: True DAG ancestry
            parent_claim_id = previous_claim.id if previous_claim else None
            parent_hashes = (
                [previous_claim.content_hash]
                if previous_claim and previous_claim.content_hash
                else []
            )

            # --- COMMIT NEW CLAIM ---
            new_claim = Claim(
                org_id=org_id,                       # ← Sprint 3.2: tenant scope
                system_id=system_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                context=context,
                entity_hint=entity_hint,
                embedding=data["embedding"],
                vector_clock=new_clock,
                content_hash=content_hash,
                parent_claim_id=parent_claim_id,
                parent_hashes=parent_hashes,
                logical_clock=logical_tick,
                is_historical=False,
            )
            db.add(new_claim)
            db.flush()
            inserted_ids.append(str(new_claim.id))

        db.commit()

        if inserted_ids:
            logger.info(
                f"SCCG Writer: Committed {len(inserted_ids)} new claims "
                f"for System [{system_id}] (org={org_id})"
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