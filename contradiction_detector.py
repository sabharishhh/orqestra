import json
import uuid
import logging
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from openai import OpenAI
from output_collector import SystemConfig, RETRYABLE_EXCEPTIONS
from claim_extractor import ExtractedClaim, clean_markdown_and_whitespace
from embedder import EmbeddedClaim, cosine_similarity
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# ==========================================
# DATA STRUCTURES
# ==========================================

@dataclass
class CandidatePair:
    claim_a: EmbeddedClaim
    claim_b: EmbeddedClaim
    cosine_similarity: float

@dataclass
class Contradiction:
    contradiction_id: str         # uuid4
    claim_a: ExtractedClaim
    claim_b: ExtractedClaim
    system_a: str
    system_b: str
    entity_hint: str
    cosine_similarity: float
    contradiction_score: float    # 0.0–1.0
    severity: str                 # critical | high | medium | low
    label: str                    # contradiction | neutral | entailment
    detected_at: datetime

# ==========================================
# NLI SYSTEM PROMPT
# ==========================================

NLI_SYSTEM_PROMPT = """You are an AI system that determines whether two statements from different AI systems are contradictory."""

# ==========================================
# CORE PIPELINE SECTIONS
# ==========================================

def find_candidate_pairs(
    claims_a: List[EmbeddedClaim], 
    claims_b: List[EmbeddedClaim], 
    threshold: float = 0.60
) -> List[CandidatePair]:
    """
    Step 1: ANN/Cosine Pre-Filter
    Compares all claims from System A against all claims from System B.
    Keeps pairs with semantic similarity >= threshold.
    """
    candidates = []
    for ca in claims_a:
        for cb in claims_b:
            sim = cosine_similarity(ca.embedding, cb.embedding)
            if sim >= threshold:
                candidates.append(CandidatePair(
                    claim_a=ca,
                    claim_b=cb,
                    cosine_similarity=sim
                ))
    return candidates


def classify_severity(entity_hint: str, score: float) -> str:
    """
    Step 4: Severity Matrix Classification
    Determines severity using the exact rule matrix mapped to corporate risk profile.
    """
    critical_domains = ["compliance", "legal", "pricing", "clinical"]
    high_domains = ["policy", "product"]
    
    normalized_hint = entity_hint.lower().strip()

    if score >= 0.85:
        if normalized_hint in critical_domains: 
            return "critical"
        if normalized_hint in high_domains:     
            return "high"
        return "medium"
    elif score >= 0.70:
        if normalized_hint in critical_domains: 
            return "high"
        return "medium"
    
    return "low"


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=4),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
def classify_pair(
    pair: CandidatePair, 
    config: SystemConfig, 
    system_a_name: str, 
    system_b_name: str
) -> Optional[Contradiction]:
    """
    Step 2 & 3: Deep NLI Evaluation
    Queries gpt-4o-mini to inspect logical overlap and structural conflict.
    """
    client_kwargs = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    client = OpenAI(**client_kwargs)
    
    # FIX: Dynamically map the Context/Domain Hint using the participating System Names.
    # This prevents the AttributeError and ensures the risk-matrix assigns financial metrics properly.
    sys_context = f"{system_a_name} {system_b_name}".lower()
    if "clinical" in sys_context or "medication" in sys_context or "discharge" in sys_context or "intake" in sys_context:
        entity_hint = "clinical"
    elif "insurance" in sys_context:
        entity_hint = "policy"
    else:
        entity_hint = getattr(pair.claim_a.claim, "subject", "general")

    # Exact verbatim prompt structure required by the specification
    nli_user_prompt = f"""Statement A (from {system_a_name}): "{pair.claim_a.claim.subject} {pair.claim_a.claim.predicate} {pair.claim_a.claim.obj}"
Statement B (from {system_b_name}): "{pair.claim_b.claim.subject} {pair.claim_b.claim.predicate} {pair.claim_b.claim.obj}"
Context topic: "{entity_hint}"

Determine the relationship:
- ENTAILMENT: both statements say the same thing
- NEUTRAL: related topic but no conflict
- CONTRADICTION: cannot both be true simultaneously

Return ONLY JSON:
{{
  "label": "ENTAILMENT" | "NEUTRAL" | "CONTRADICTION",
  "score": 0.0-1.0,
  "reasoning": "one sentence"
}}"""

    try:
        response = client.chat.completions.create(
            model=config.model if config.model else "gpt-4o-mini",
            messages=[
                {"role": "system", "content": NLI_SYSTEM_PROMPT},
                {"role": "user", "content": nli_user_prompt}
            ],
            temperature=0.0
        )
        
        raw_content = response.choices[0].message.content or ""
        cleaned_json = clean_markdown_and_whitespace(raw_content)
        data = json.loads(cleaned_json)
        
        label = str(data.get("label", "")).upper().strip()
        score = float(data.get("score", 0.0))
        
        # Rule filter verification step: strict check on contradiction and threshold barriers
        if label == "CONTRADICTION" and score >= 0.70:
            severity = classify_severity(entity_hint, score)
            
            return Contradiction(
                contradiction_id=str(uuid.uuid4()),
                claim_a=pair.claim_a.claim,
                claim_b=pair.claim_b.claim,
                system_a=system_a_name,
                system_b=system_b_name,
                entity_hint=entity_hint,
                cosine_similarity=pair.cosine_similarity,
                contradiction_score=score,
                severity=severity,
                label="contradiction",
                detected_at=datetime.now(timezone.utc)
            )
            
        return None
        
    except Exception as e:
        logger.error(f"Failed to perform NLI evaluation on claim pair: {e}")
        return None


def run_detection(
    claims_a: List[EmbeddedClaim], 
    claims_b: List[EmbeddedClaim], 
    config: SystemConfig, 
    system_a_name: str, 
    system_b_name: str,
    similarity_threshold: float = 0.60
) -> List[Contradiction]:
    """
    Executes the comprehensive detection funnel on two blocks of claims.
    Returns any validated factual conflicts.
    """
    # 1. Filter out pairs that are not semantically close
    candidate_pairs = find_candidate_pairs(claims_a, claims_b, threshold=similarity_threshold)
    
    contradictions = []
    
    # 2. Inspect remaining candidates using deep NLI verification loops
    for pair in candidate_pairs:
        result = classify_pair(pair, config, system_a_name, system_b_name)
        if result:
            contradictions.append(result)
            
    return contradictions