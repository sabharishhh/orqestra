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
    Calculates running belief_variance and confidence scores per F1.5 Spec.
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
                    sample_count=1,
                    belief_variance=0.0,
                    confidence=0.1 * 1.0 * 1.0, # min(1.0, 1/10) * recency_weight(1.0) * (1 - var(0.0))
                    recency_weight=1.0,
                    staleness_score=0.0
                )
                db.add(belief_state)
            else:
                # --- ISSUE-10 / F1.5 FIX: Welford's Math for Variance & Mean ---
                current_centroid = np.array(belief_state.centroid_embedding)
                current_count = belief_state.sample_count
                current_variance = belief_state.belief_variance or 0.0
                
                new_count = current_count + 1
                
                # 1. Update Mean (Centroid)
                delta = new_vector - current_centroid
                updated_centroid = current_centroid + delta / new_count
                
                # 2. Update Variance (Welford's Second Moment)
                delta2 = new_vector - updated_centroid
                # S is the sum of squared differences. S = variance * count
                s_old = current_variance * current_count
                s_new = s_old + np.sum(delta * delta2)
                new_variance = float(s_new / new_count)
                
                # 3. Calculate F1.5 Confidence Score
                # Formula: min(1.0, n/10) * recency_weight * (1 - variance)
                recency = belief_state.recency_weight or 1.0
                
                # Safety clamp for variance to prevent negative confidence on extreme outliers
                clamped_variance = min(1.0, max(0.0, new_variance))
                new_confidence = float(min(1.0, new_count / 10.0) * recency * (1.0 - clamped_variance))
                
                # Commit updates to the OBG node
                belief_state.centroid_embedding = updated_centroid.tolist()
                belief_state.sample_count = new_count
                belief_state.belief_variance = new_variance
                belief_state.confidence = new_confidence
                
            db.flush()

        db.commit()
        logger.info(f"OBG Updater: Shifted centroids & variance for {len(updated_entities)} entities.")
        return list(updated_entities)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Critical OBG Welford Update Failure: {e}")
        raise
    finally:
        db.close()