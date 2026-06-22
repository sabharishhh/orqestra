import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from openai import OpenAI
from output_collector import SystemConfig, RETRYABLE_EXCEPTIONS
from claim_extractor import clean_markdown_and_whitespace
from contradiction_detector import Contradiction
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# ==========================================
# DATA STRUCTURES
# ==========================================

@dataclass
class Explanation:
    contradiction_id: str
    why_they_contradict: str         # 2-3 sentences, plain English, no jargon
    likely_stale_system: str         # "A" | "B" | "unknown"
    staleness_reasoning: str         # one sentence
    risk_level: str                  # "critical" | "high" | "medium" | "low"
    risk_reason: str                 # one sentence, specific business consequence
    recommended_action: str          # one actionable sentence starting with a verb
    system_a_name: str
    system_b_name: str
    system_a_claim: str
    system_b_claim: str
    system_a_full_output: str
    system_b_full_output: str
    estimated_cost_if_unresolved: str   # from lookup table, NOT LLM-generated
    slack_summary: str               # <120 chars, one line
    generated_at: datetime

# ==========================================
# COST LOOKUP MATRIX (Fault Registry F2.4 Guardrail)
# ==========================================

COST_RANGES: Dict[tuple, str] = {
    ("high",     "consumer"):    "$1,200 (Subscription Cancellation + LTV Loss)",
    ("medium",   "consumer"):    "$150 (Customer Support Escalation Ticket)",
    ("critical", "clinical"):    "$300,000–$500,000 (malpractice exposure)",
    ("critical", "compliance"):  "$50,000–$250,000 (regulatory fine)",
    ("critical", "pricing"):     "$5,000–$50,000 (contract/billing dispute)",
    ("critical", "legal"):       "$50,000–$500,000 (legal liability)",
    ("high",     "policy"):      "$1,000–$15,000 (customer incident + eng time)",
    ("high",     "product"):     "$500–$5,000 (support cost + churn risk)",
    ("medium",   "general"):     "$150–$1,000 (engineering resolution time)",
    ("low",      "general"):     "$150–$300 (engineering time)",
}

def estimate_cost(severity: str, entity_hint: str) -> str:
    """
    Returns a deterministic financial risk range.
    Never allows the LLM to invent business exposure numbers.
    """
    sev = severity.lower().strip()
    hint = entity_hint.lower().strip()
    
    # Try the specific combination first
    if (sev, hint) in COST_RANGES:
        return COST_RANGES[(sev, hint)]
        
    # Fall back to general baseline for that severity tier
    if (sev, "general") in COST_RANGES:
        return COST_RANGES[(sev, "general")]
        
    return "$150–$300 (engineering time)"

# ==========================================
# EXPLANATION PROMPT
# ==========================================

EXPLANATION_SYSTEM_PROMPT = """You are an AI coherence analyst. Two AI systems have made contradictory statements. Analyse the contradiction and provide a complete, actionable explanation."""

# ==========================================
# CORE GENERATION ENGINE
# ==========================================

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=4),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
def explain(contradiction: Contradiction, config: SystemConfig) -> Explanation:
    """
    Analyzes a confirmed system mismatch and compiles a structural risk footprint.
    Uses quality critical GPT-5.4-mini engine to ensure enterprise-ready explanations.
    """
    # Ensure we force the explanation agent to use premium GPT-5.4-mini as locked in the specs
    execution_model = "gpt-5.4-mini"

    client_kwargs = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    client = OpenAI(**client_kwargs)

    # Reconstruct localized claims for context injection
    claim_a_text = f"{contradiction.claim_a.subject} {contradiction.claim_a.predicate} {contradiction.claim_a.obj}"
    claim_b_text = f"{contradiction.claim_b.subject} {contradiction.claim_b.predicate} {contradiction.claim_b.obj}"

    # Verbatim Master Prompt specification formatting
    user_prompt = f"""SYSTEM A: {contradiction.system_a}
Claim A: "{claim_a_text}"
Full output A: "{contradiction.claim_a.context}"

SYSTEM B: {contradiction.system_b}
Claim B: "{claim_b_text}"
Full output B: "{contradiction.claim_b.context}"

Topic: {contradiction.entity_hint}
Contradiction score: {contradiction.contradiction_score}

Return ONLY JSON with exactly these fields:
{{
  "why_they_contradict": "2-3 sentences plain English. What specifically contradicts and why both cannot be correct. Write for a VP Engineering. No technical jargon.",
  "likely_stale_system": "A" or "B" or "unknown",
  "staleness_reasoning": "One sentence on which system is probably outdated and why.",
  "risk_level": "critical" or "high" or "medium" or "low",
  "risk_reason": "One sentence. Specific real-world consequence if not fixed.",
  "recommended_action": "One specific actionable sentence starting with a verb. Not 'review this.' Tell them exactly what to do.",
  "slack_summary": "One line under 120 chars: [SYS_A] says X but [SYS_B] says Y — likely stale: [SYS]. Risk: [LEVEL]."
}}"""

    try:
        response = client.chat.completions.create(
            model=execution_model,
            messages=[
                {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0
        )
        
        raw_content = response.choices[0].message.content or ""
        cleaned_json = clean_markdown_and_whitespace(raw_content)
        data = json.loads(cleaned_json)

        # Apply deterministic cost tracking calculations safely outside the LLM context
        cost_estimation = estimate_cost(contradiction.severity, contradiction.entity_hint)

        return Explanation(
            contradiction_id=contradiction.contradiction_id,
            why_they_contradict=str(data.get("why_they_contradict", "")).strip(),
            likely_stale_system=str(data.get("likely_stale_system", "unknown")).strip(),
            staleness_reasoning=str(data.get("staleness_reasoning", "")).strip(),
            risk_level=str(data.get("risk_level", contradiction.severity)).strip(),
            risk_reason=str(data.get("risk_reason", "")).strip(),
            recommended_action=str(data.get("recommended_action", "")).strip(),
            system_a_name=contradiction.system_a,
            system_b_name=contradiction.system_b,
            system_a_claim=claim_a_text,
            system_b_claim=claim_b_text,
            system_a_full_output=contradiction.claim_a.context,
            system_b_full_output=contradiction.claim_b.context,
            estimated_cost_if_unresolved=cost_estimation,
            slack_summary=str(data.get("slack_summary", "")).strip(),
            generated_at=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Critical failure inside explain generation loop: {e}")
        # Build an operational fallback to guarantee the dashboard/pipeline never breaks entirely
        return Explanation(
            contradiction_id=contradiction.contradiction_id,
            why_they_contradict="System warning: Failed to extract automated explanation analysis payload context.",
            likely_stale_system="unknown",
            staleness_reasoning="Pipeline processing error.",
            risk_level=contradiction.severity,
            risk_reason="A cross-system variance remains un-remediated due to explanation parsing bottlenecks.",
            recommended_action="Manually evaluate raw data context traces attached below.",
            system_a_name=contradiction.system_a,
            system_b_name=contradiction.system_b,
            system_a_claim=claim_a_text,
            system_b_claim=claim_b_text,
            system_a_full_output=contradiction.claim_a.context,
            system_b_full_output=contradiction.claim_b.context,
            estimated_cost_if_unresolved=estimate_cost(contradiction.severity, contradiction.entity_hint),
            slack_summary=f"Alert: Unresolved divergence detected between {contradiction.system_a} and {contradiction.system_b}.",
            generated_at=datetime.utcnow()
        )


def explain_batch(contradictions: List[Contradiction], config: SystemConfig) -> List[Explanation]:
    """Processes explanation summaries sequentially for a batch of confirmed contradictions."""
    explanations = []
    for c in contradictions:
        explanations.append(explain(c, config))
    return explanations