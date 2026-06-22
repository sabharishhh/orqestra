import os
import json
import logging
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim, Contradiction
from openai import OpenAI

logger = logging.getLogger(__name__)

NLI_SYSTEM_PROMPT = "You determine whether two statements from different AI systems are contradictory."

def calculate_severity(entity: str, score: float) -> str:
    """Matches our dynamic matrix from Phase 0."""
    normalized = entity.lower().strip()
    critical_domains = ["compliance", "legal", "pricing", "clinical"]
    high_domains = ["policy", "product", "consumer", "weekly schedule", "monthly food selection", "workout routine exercises"]
    
    if score >= 0.85:
        if normalized in critical_domains: return "critical"
        if normalized in high_domains: return "high"
        return "medium"
    elif score >= 0.70:
        if normalized in critical_domains: return "high"
        return "medium"
    return "low"

def run_5_level_funnel(system_id: str, updated_entities: list) -> list:
    """
    Worker 4 Phase: Implements the 5-Level Detection Funnel using Postgres pgvector.
    """
    if not updated_entities:
        return []
        
    db: Session = SessionLocal()
    contradiction_ids = []
    
    try:
        new_claims = db.query(Claim).filter(
            Claim.system_id == system_id,
            Claim.entity_hint.in_(updated_entities)
        ).all()
        
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        
        for new_claim in new_claims:
            neighbors = db.query(Claim).filter(
                Claim.system_id != system_id,
                Claim.entity_hint == new_claim.entity_hint,
                Claim.embedding.cosine_distance(new_claim.embedding) <= 0.40
            ).limit(5).all()
            
            for neighbor in neighbors:
                nli_prompt = f"""Statement A: "{new_claim.subject} {new_claim.predicate} {new_claim.object}"
Statement B: "{neighbor.subject} {neighbor.predicate} {neighbor.object}"
Context topic: "{new_claim.entity_hint}"

Return ONLY JSON:
{{
  "label": "ENTAILMENT" | "NEUTRAL" | "CONTRADICTION",
  "score": 0.0-1.0,
  "reasoning": "one sentence"
}}"""
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": NLI_SYSTEM_PROMPT},
                        {"role": "user", "content": nli_prompt}
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
                
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                    
                if data.get("label") == "CONTRADICTION" and data.get("score", 0.0) >= 0.70:
                    id_a, id_b = sorted([str(new_claim.id), str(neighbor.id)])
                    
                    exists = db.query(Contradiction).filter_by(claim_a_id=id_a, claim_b_id=id_b).first()
                    if not exists:
                        severity = calculate_severity(new_claim.entity_hint, data.get("score"))
                        
                        contra = Contradiction(
                            claim_a_id=id_a,
                            claim_b_id=id_b,
                            cosine_similarity=0.85, 
                            nli_score=data.get("score"),
                            severity=severity
                        )
                        db.add(contra)
                        db.flush()
                        contradiction_ids.append(str(contra.id))
                        
        db.commit()
        return contradiction_ids
        
    except Exception as e:
        db.rollback()
        logger.error(f"Detection funnel failed: {e}")
        raise
    finally:
        db.close()