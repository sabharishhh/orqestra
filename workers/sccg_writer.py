import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim

logger = logging.getLogger(__name__)

def write_claims_to_sccg(system_id: str, embedded_claims_data: List[Dict]) -> List[str]:
    """
    Writes deeply extracted claims into the SCCG Postgres table.
    Enforces F8.4 Append-Only Guardrails.
    """
    if not embedded_claims_data:
        return []

    inserted_ids = []
    db: Session = SessionLocal()
    
    try:
        for data in embedded_claims_data:
            # We derive the entity_hint dynamically from the subject
            # (In production, this would use a dedicated lightweight NER tagger)
            entity_hint = str(data["claim"].get("subject", "general")).lower().strip()

            new_claim = Claim(
                system_id=system_id,
                subject=data["claim"]["subject"],
                predicate=data["claim"]["predicate"],
                object=data["claim"].get("object", data["claim"].get("obj", "")),
                context=data["claim"]["context"],
                entity_hint=entity_hint,
                embedding=data["embedding"],
                vector_clock={"origin_system": system_id, "v": 1},
                parent_hashes=[] 
            )
            db.add(new_claim)
            db.flush() # Flush to get the ID without committing the whole transaction yet
            inserted_ids.append(str(new_claim.id))
            
        db.commit()
        logger.info(f"SCCG Writer: Committed {len(inserted_ids)} new claims for System [{system_id}]")
        return inserted_ids
        
    except Exception as e:
        db.rollback()
        logger.error(f"Critical SCCG Write Failure: {e}")
        raise
    finally:
        db.close()