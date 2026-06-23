import logging
import hashlib
from typing import List, Dict
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim

logger = logging.getLogger(__name__)

def write_claims_to_sccg(system_id: str, embedded_claims_data: List[Dict]) -> List[str]:
    """
    Writes deeply extracted claims into the SCCG Postgres table.
    Enforces F8.4 Append-Only Guardrails, Level 2 Deduplication,
    and calculates Dynamic Vector Clocks (Fixes Blocker #3).
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
            
            # We derive the entity_hint dynamically from the subject
            entity_hint = str(subject).lower().strip()

            # --- LEVEL 2: CONTENT HASHING (Cryptographic Deduplication) ---
            # Create a deterministic fingerprint of the core factual triad
            raw_string = f"{subject}|{predicate}|{obj}".lower().encode('utf-8')
            content_hash = hashlib.sha256(raw_string).hexdigest()
            
            # Check if this exact fact has already been ingested by this system.
            is_duplicate = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.parent_hashes.contains([content_hash])
            ).first()
            
            if is_duplicate:
                logger.info(f"Level 2 Funnel: Dropping duplicate claim. Hash [{content_hash[:8]}] already exists for System.")
                continue

            # --- DYNAMIC VECTOR CLOCK MATH (Fixes Blocker #3) ---
            # Fetch the previous vector clock for this specific (System + Entity)
            previous_claim = db.query(Claim).filter(
                Claim.system_id == system_id,
                Claim.entity_hint == entity_hint
            ).order_by(Claim.extracted_at.desc()).first()

            # Inherit the old clock, or start fresh if this is the first claim
            new_clock = previous_claim.vector_clock.copy() if previous_claim and previous_claim.vector_clock else {}
            
            # Increment the tick for this system's node
            sys_key = str(system_id)
            new_clock[sys_key] = new_clock.get(sys_key, 0) + 1

            # --- COMMIT NEW CLAIM ---
            new_claim = Claim(
                system_id=system_id,
                subject=subject,
                predicate=predicate,
                object=obj,
                context=context,
                entity_hint=entity_hint,
                embedding=data["embedding"],
                vector_clock=new_clock,  # Now dynamically incrementing!
                parent_hashes=[content_hash],  # Store the fingerprint for future deduplication
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