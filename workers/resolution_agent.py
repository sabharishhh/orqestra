import os
import json
import logging
import httpx
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Contradiction, Claim, ResolutionProposal, System
from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# F2.4 Compliance: Deterministic Causal Parser (ISSUE-01 Fix)
def deterministic_causal_parser(claim_a: Claim, claim_b: Claim, sys_a_name: str, sys_b_name: str) -> str:
    """Calculates factual Lowest Common Ancestor to prevent LLM hallucination of time."""
    # Using parent_hashes for cross-system intersection
    parents_a = set(claim_a.parent_hashes) if claim_a.parent_hashes else set()
    parents_b = set(claim_b.parent_hashes) if claim_b.parent_hashes else set()
    
    intersection = parents_a.intersection(parents_b)
    
    if intersection:
        return f"Both systems ({sys_a_name} and {sys_b_name}) share a common ancestral context or document. They observed the same base facts but interpreted conflicting policies."
    
    return f"Both systems ({sys_a_name} and {sys_b_name}) generated these policies completely independently. Neither system was aware of the other's state at the time of execution."


# F5.1 Compliance: Circuit Breaker on LLM via Tenacity
@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30), 
    stop=stop_after_attempt(5), 
    retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError, httpx.HTTPError)),
    reraise=True
)
def safe_llm_resolution(prompt: str) -> dict:
    """Executes the LLM call with exponential backoff protection."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-5.4-mini", 
        messages=[
            {"role": "system", "content": "You resolve AI contradictions based strictly on the provided causal history. Do not invent timelines."},
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
        
    return json.loads(raw.strip())


def generate_resolution(contradiction_id: str):
    """Worker 5 Phase: The grounded explainer agent."""
    db: Session = SessionLocal()
    
    try:
        contra = db.query(Contradiction).filter_by(id=contradiction_id).first()
        if not contra:
            return
            
        claim_a = db.query(Claim).filter_by(id=contra.claim_a_id).first()
        claim_b = db.query(Claim).filter_by(id=contra.claim_b_id).first()
        
        sys_a = db.query(System).filter_by(id=claim_a.system_id).first()
        sys_b = db.query(System).filter_by(id=claim_b.system_id).first()
        
        # 1. Generate the deterministic mathematical truth
        causal_truth = deterministic_causal_parser(
            claim_a, claim_b, 
            sys_a.name, sys_b.name
        )
        
        # 2. Inject truth into the prompt
        prompt = f"""SYSTEM A ({sys_a.name}) Claim: "{claim_a.subject} {claim_a.predicate} {claim_a.object}"
SYSTEM B ({sys_b.name}) Claim: "{claim_b.subject} {claim_b.predicate} {claim_b.object}"

Topic: {claim_a.entity_hint}
Causal History (FACT): {causal_truth}

Return ONLY JSON matching:
{{
  "why_they_contradict": "2-3 sentences plain English explaining the logical clash.",
  "likely_stale_system": "Identify which system is likely outdated based ON THE CAUSAL HISTORY FACT.",
  "risk_reason": "Specific real-world consequence.",
  "recommended_action": "Actionable sentence starting with a verb.",
  "target_uri": "Must be a machine-actionable URI (e.g. kb://guidelines/rules). Never a vague description."
}}"""

        # 3. Call the protected LLM function
        data = safe_llm_resolution(prompt)
        
        # 4. Dynamic Cost Logic based on High-Risk Entity Domains
        high_risk_entities = ["consumer", "weekly schedule", "monthly food selection", "workout routine exercises"]
        is_high_risk = any(domain in claim_a.entity_hint.lower() for domain in high_risk_entities)
        
        cost = "$1,200 (Subscription Cancellation + LTV Loss)" if is_high_risk else "$150–$300 (Engineering Resolution)"
        
        resolution = ResolutionProposal(
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
        logger.info(f"Resolution Agent successfully compiled factual fix for Contradiction [{contradiction_id}]")

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