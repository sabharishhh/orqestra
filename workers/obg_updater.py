import logging
import numpy as np
from typing import List
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim, EntityBeliefState

logger = logging.getLogger(__name__)

def update_entity_centroids(system_id: str, new_claim_ids: List[str]) -> List[str]:
    """
    Updates the Organizational Belief Graph (OBG) using Welford's online algorithm.
    This maintains a running vector centroid for what a system 'believes' about an entity.
    """
    if not new_claim_ids:
        return []

    db: Session = SessionLocal()
    updated_entities = set()
    
    try:
        # Fetch the actual claims we just inserted
        claims = db.query(Claim).filter(Claim.id.in_(new_claim_ids)).all()
        
        for claim in claims:
            entity_name = claim.entity_hint
            if not entity_name:
                continue
                
            updated_entities.add(entity_name)
            new_vector = np.array(claim.embedding)
            
            # Lock the belief state row for an atomic Welford update
            belief_state = db.query(EntityBeliefState).filter_by(
                system_id=system_id, 
                entity_name=entity_name
            ).with_for_update().first()
            
            if not belief_state:
                # First time this system has mentioned this entity
                belief_state = EntityBeliefState(
                    system_id=system_id,
                    entity_name=entity_name,
                    centroid_embedding=new_vector.tolist(),
                    sample_count=1
                )
                db.add(belief_state)
            else:
                # Welford's Online Algorithm for calculating running mean (centroid)
                current_centroid = np.array(belief_state.centroid_embedding)
                current_count = belief_state.sample_count
                
                # new_mean = current_mean + (new_value - current_mean) / new_count
                new_count = current_count + 1
                updated_centroid = current_centroid + (new_vector - current_centroid) / new_count
                
                belief_state.centroid_embedding = updated_centroid.tolist()
                belief_state.sample_count = new_count
                
            db.flush()

        db.commit()
        logger.info(f"OBG Updater: Shifted centroids for {len(updated_entities)} entities.")
        return list(updated_entities)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Critical OBG Welford Update Failure: {e}")
        raise
    finally:
        db.close()