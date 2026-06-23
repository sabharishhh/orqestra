import os
import json
import logging
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Contradiction, Claim, Resolution, System
from openai import OpenAI

# Removed the top-level import of workers.tasks to prevent circular dependency

logger = logging.getLogger(__name__)

def generate_resolution(contradiction_id: str):
    """Worker 5 Phase: The premium GPT-5.4 explainer agent."""
    db: Session = SessionLocal()
    
    try:
        contra = db.query(Contradiction).filter_by(id=contradiction_id).first()
        if not contra:
            return
            
        claim_a = db.query(Claim).filter_by(id=contra.claim_a_id).first()
        claim_b = db.query(Claim).filter_by(id=contra.claim_b_id).first()
        
        sys_a = db.query(System).filter_by(id=claim_a.system_id).first()
        sys_b = db.query(System).filter_by(id=claim_b.system_id).first()
        
        vc_a = json.dumps(claim_a.vector_clock)
        vc_b = json.dumps(claim_b.vector_clock)
        
        prompt = f"""SYSTEM A ({sys_a.name}) Vector Clock: {vc_a}
Claim A: "{claim_a.subject} {claim_a.predicate} {claim_a.object}"

SYSTEM B ({sys_b.name}) Vector Clock: {vc_b}
Claim B: "{claim_b.subject} {claim_b.predicate} {claim_b.object}"

Topic: {claim_a.entity_hint}

Return ONLY JSON matching:
{{
  "why_they_contradict": "2-3 sentences plain English.",
  "likely_stale_system": "A or B",
  "risk_reason": "Specific real-world consequence.",
  "recommended_action": "Actionable sentence starting with a verb.",
  "target_uri": "Must be a machine-actionable URI (e.g. kb://guidelines/rules). Never a vague description."
}}"""

        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-5.4-mini", 
            messages=[
                {"role": "system", "content": "You resolve AI contradictions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        
        # Safely parse JSON blocks
        raw = response.choices[0].message.content.strip()
        if raw.startswith('```json'):
            raw = raw[7:]
        if raw.endswith('```'):
            raw = raw[:-3]
        raw = raw.strip()
        
        data = json.loads(raw)
        
        # Dynamic Cost Logic based on High-Risk Entity Domains
        high_risk_entities = ["consumer", "weekly schedule", "monthly food selection", "workout routine exercises"]
        is_high_risk = any(domain in claim_a.entity_hint.lower() for domain in high_risk_entities)
        
        # Use is_high_risk to trigger the $1,200 tier instead of the old is_consumer check
        cost = "$1,200 (Subscription Cancellation + LTV Loss)" if is_high_risk else "$150–$300 (Engineering Resolution)"
        
        resolution = Resolution(
            contradiction_id=contradiction_id,
            why_they_contradict=data.get("why_they_contradict", ""),
            likely_stale_system=data.get("likely_stale_system", "Unknown"),
            risk_reason=data.get("risk_reason", ""),
            recommended_action=data.get("recommended_action", ""),
            estimated_cost=cost,
            target_uri=data.get("target_uri", "kb://unknown-source")
        )
        
        db.add(resolution)
        db.commit()
        logger.info(f"Resolution Agent successfully compiled fix for Contradiction [{contradiction_id}]")

        if is_high_risk:
            logger.info("High risk detected. Triggering Slack Webhook Dispatcher...")
            from workers.tasks import dispatch_alert_task
            dispatch_alert_task.delay(str(resolution.id))
        
    except Exception as e:
        db.rollback()
        logger.error(f"Resolution agent failed: {e}")
        raise
    finally:
        db.close()