import os
import json
import logging
from observability import get_logger

import httpx
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import Contradiction, Claim, Resolution, System
from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = get_logger(__name__)


# Severity tiers that warrant an immediate alert dispatch (Slack/email/etc).
# Defined as a constant rather than a list of entity names so the policy
# is uniform across all verticals (a 'critical' clinical contradiction and
# a 'critical' consumer contradiction are equally alert-worthy).
ALERT_TIERS = {"critical", "high"}


# F2.4 Compliance: Deterministic Causal Parser (ISSUE-01 Fix)
def deterministic_causal_parser(claim_a: Claim, claim_b: Claim, sys_a_name: str, sys_b_name: str) -> str:
    """Calculates factual Lowest Common Ancestor to prevent LLM hallucination of time."""
    parents_a = set(claim_a.parent_hashes) if claim_a.parent_hashes else set()
    parents_b = set(claim_b.parent_hashes) if claim_b.parent_hashes else set()

    intersection = parents_a.intersection(parents_b)

    if intersection:
        return (
            f"Both systems ({sys_a_name} and {sys_b_name}) share a common ancestral "
            f"context or document. They observed the same base facts but interpreted "
            f"conflicting policies."
        )

    return (
        f"Both systems ({sys_a_name} and {sys_b_name}) generated these policies "
        f"completely independently. Neither system was aware of the other's state "
        f"at the time of execution."
    )


def _format_cost(cost_usd: int, severity: str) -> str:
    """
    Format the dollar cost as a human-readable string for the Resolution row.
    The number comes from severity_scorer.calculate_severity_and_cost(),
    which read from the canonical entity's cost_high_usd/cost_critical_usd.
    No hardcoded multipliers here.
    """
    if cost_usd <= 0:
        return "Negligible (sub-threshold)"
    descriptor = {
        "critical": "Critical exposure",
        "high":     "High exposure",
        "medium":   "Moderate exposure",
        "low":      "Low exposure",
    }.get(severity, "Exposure")
    return f"${cost_usd:,} ({descriptor})"


# F5.1 Compliance: Circuit Breaker on LLM via Tenacity
@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError, httpx.HTTPError)),
    reraise=True,
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
        temperature=0.0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith('```json'):
        raw = raw[7:]
    if raw.endswith('```'):
        raw = raw[:-3]

    return json.loads(raw.strip())


def generate_resolution(contradiction_id: str):
    """Worker 5 Phase: The grounded explainer agent (multi-tenant)."""
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
            sys_a.name, sys_b.name,
        )

        # 2. Inject truth into the prompt
        prompt = f"""SYSTEM A ({sys_a.name}) Claim: "{claim_a.subject} {claim_a.predicate} {claim_a.object}"
SYSTEM B ({sys_b.name}) Claim: "{claim_b.subject} {claim_b.predicate} {claim_b.object}"

Topic: {claim_a.entity_hint}
Severity: {contra.severity}
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

        # 4. Cost & severity come from severity_scorer's earlier decision,
        #    persisted on the Contradiction row. No hardcoded entity lists
        #    or cost constants here — the per-org canonical_entities table
        #    is the single source of truth for both.
        cost_str = _format_cost(contra.cost_usd or 0, contra.severity)

        resolution = Resolution(
            contradiction_id=contradiction_id,
            why_they_contradict=data.get("why_they_contradict", ""),
            likely_stale_system=data.get("likely_stale_system", "Unknown"),
            risk_reason=data.get("risk_reason", ""),
            recommended_action=data.get("recommended_action", ""),
            estimated_cost=cost_str,
            target_uri=data.get("target_uri", "kb://unknown-source"),
        )

        db.add(resolution)
        db.commit()
        logger.info(
            f"Resolution Agent compiled fix for Contradiction [{contradiction_id}] "
            f"(severity={contra.severity}, cost={cost_str})"
        )

        # 5. Alert dispatch based on declared tier, uniform across verticals
        if contra.severity in ALERT_TIERS:
            logger.info(f"Severity={contra.severity}. Triggering alert dispatcher...")
            from workers.tasks import dispatch_alert_task
            dispatch_alert_task.delay(str(resolution.id))

    except Exception as e:
        db.rollback()
        logger.error(f"Resolution agent failed: {e}")
        raise
    finally:
        db.close()