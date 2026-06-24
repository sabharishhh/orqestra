import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim
from services.content_hasher import normalize_and_hash # F1.2 / ISSUE-15 FIX
from services.entity_resolver import resolve_entity_hint

logger = logging.getLogger(__name__)

def write_claims_to_sccg(system_id: str, embedded_claims_data: List[Dict]) -> List[str]:
    """
    Writes deeply extracted claims into the SCCG Postgres table.
    Enforces F8.4 Append-Only Guardrails, Level 2 Deduplication,
    calculates Dynamic Vector Clocks, and maintains strict Merkle ancestry.
    """
    if not embedded_claims_data:
        return []

    inserted_ids = []
    db: Session = SessionLocal()
    
    try:
        for data in embedded_claims_data:
            subject = data["claim"]["subject"]
            predicate = data["claim"]["predicate"]
            obj = data["claim"].get("object", data["claim"].get("obj", ""))
            context = data["claim"]["context"]
            
            # --- ISSUE-03 FIX: Entity Hint Normalization ---
            raw_hint = data["claim"].get("entity_hint", "general")
            entity_hint = resolve_entity_hint(
                raw_hint,
                embedding=data["embedding"],
                db=db
            )

            # --- LEVEL 2: CONTENT HASHING (ISSUE-15 & ISSUE-05 FIX) ---
            # Uses the external service to strip hedges/noise
            content_hash = normalize_and_hash(subject, predicate, obj)
            
            # Deduplication now correctly uses the dedicated content_hash column, NOT parent_hashes
            is_duplicate = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.content_hash == content_hash
            ).first()
            
            if is_duplicate:
                logger.info(f"Level 2 Funnel: Dropping duplicate claim. Hash [{content_hash[:8]}] already exists for System.")
                continue

            # --- DYNAMIC VECTOR CLOCK & ANCESTRY MATH ---
            previous_claim = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.entity_hint == entity_hint
            ).order_by(Claim.extracted_at.desc()).first()

            # Inherit the old clock, or start fresh if this is the first claim
            new_clock = previous_claim.vector_clock.copy() if previous_claim and previous_claim.vector_clock else {}
            
            # Increment the tick for this system's node
            sys_key = str(system_id)
            logical_tick = new_clock.get(sys_key, 0) + 1
            new_clock[sys_key] = logical_tick

            # F2.4 / ISSUE-05 Fix: Determine true Directed Acyclic Graph (DAG) ancestry
            parent_claim_id = previous_claim.id if previous_claim else None
            parent_hashes = [previous_claim.content_hash] if previous_claim and previous_claim.content_hash else []

            # --- COMMIT NEW CLAIM ---
            new_claim = Claim(
                system_id=system_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                context=context,
                entity_hint=entity_hint,
                embedding=data["embedding"],
                vector_clock=new_clock,
                content_hash=content_hash,         # Own hash goes here
                parent_claim_id=parent_claim_id,   # Graph FK goes here
                parent_hashes=parent_hashes,       # Ancestor hash goes here
                logical_clock=logical_tick,        # Integer tick goes here
                is_historical=False # F4.4 Compliance
            )
            db.add(new_claim)
            db.flush() # Flush to get the ID without committing the whole transaction yet
            inserted_ids.append(str(new_claim.id))
            
        db.commit()
        
        if inserted_ids:
            logger.info(f"SCCG Writer: Committed {len(inserted_ids)} new claims for System [{system_id}]")
        else:
            logger.info(f"SCCG Writer: 0 new claims committed for System [{system_id}] (All duplicates dropped)")
            
        return inserted_ids
        
    except Exception as e:
        db.rollback()
        logger.error(f"Critical SCCG Write Failure: {e}")
        raise
    finally:
        db.close()