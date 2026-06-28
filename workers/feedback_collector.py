import logging
from observability import get_logger
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Contradiction, Resolution, ContrastiveFeedback, Entity
from core.celery_app import celery_app

logger = get_logger(__name__)

@celery_app.task(queue="claim_extraction")
def record_feedback(proposal_id: str, action: str):
    """Worker 8: Contrastive feedback loop for Reinforcement Learning."""
    db: Session = SessionLocal()
    try:
        # FIXED: Querying the Resolution table
        proposal = db.query(Resolution).filter_by(id=proposal_id).first()
        if not proposal:
            logger.error(f"Feedback Collector: Proposal {proposal_id} not found.")
            return

        contradiction = db.query(Contradiction).filter_by(id=proposal.contradiction_id).first()
        
        # Resolve the entity type dynamically
        entity = db.query(Entity).filter_by(id=contradiction.entity_id).first() if contradiction.entity_id else None
        entity_type = entity.entity_type if entity else "general"

        # 1. Create the RL Reward Signal
        feedback = ContrastiveFeedback(
            contradiction_id=proposal.contradiction_id,
            claim_a_id=contradiction.claim_a_id,
            claim_b_id=contradiction.claim_b_id,
            entity_type=entity_type,
            nli_label="contradiction" if action == "accept" else "neutral",
            is_hard_negative=(action == "reject"),
            feedback_source="proposal_accepted" if action == "accept" else "proposal_rejected"
        )
        db.add(feedback)
        db.commit()

        # 2. Check F3.2 Compliance (Domain-Scoped Thresholds)
        count = db.query(ContrastiveFeedback).filter_by(entity_type=entity_type).count()
        logger.info(f"Feedback recorded for {entity_type}. Total domain examples: {count}")
        
        if count >= 50 and count % 50 == 0:
            logger.info(f"Domain threshold reached for '{entity_type}'. Triggering DeBERTa fine-tuning pipeline.")
            from workers.tasks import trigger_finetune_task
            trigger_finetune_task.delay(entity_type=entity_type)

    except Exception as e:
        db.rollback()
        logger.error(f"Feedback collector failed: {e}")
    finally:
        db.close()