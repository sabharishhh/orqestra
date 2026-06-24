import os
import json
import logging
from typing import List, Dict, Any
import httpx
from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# --- ISSUE-03 FIX: Added critical instruction for normalized entity_hint ---
EXTRACTION_SYSTEM_PROMPT = """You are a precise operational data extraction engine.
Your task is to decompose raw text into an explicit array of factual claims represented as Subject-Predicate-Object (SPO) triples with a strict contextual modifier.

CRITICAL: For each claim, you MUST set `entity_hint` to ONE value from this CLOSED vocabulary. Do not invent new hints. Pick the single closest match:

ALLOWED entity_hint values:
- workout_schedule       (weekly training days, rest days, schedule allocation)
- workout_routine        (specific exercises, movement selection, what to do/avoid)
- meal_plan              (food choices, meal selection, organic/processed selection)
- nutrition_macros       (calorie targets, macro breakdown, deficit/surplus)
- sleep_target           (sleep duration, rest hours)
- activity_limit         (session duration limits, max minutes per workout)
- food_budget_policy     (food spending limits, eliminating premium options to save money)
- fitness_budget_policy  (gym memberships, fitness equipment, home vs gym workouts)
- general                (only when nothing else fits)

Return ONLY JSON matching:
{
  "claims": [
    {
      "subject": "string",
      "predicate": "string",
      "object": "string",
      "context": "string",
      "entity_hint": "string (MUST be from the allowed list above)"
    }
  ]
}"""

# F5.1 Compliance: Circuit Breaker on LLM via Tenacity with explicit exception typing
@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30), 
    stop=stop_after_attempt(5), 
    retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError, httpx.HTTPError)),
    reraise=True
)
def run_extraction(text: str) -> List[Dict[str, Any]]:
    """Worker 1 Phase: Extracts structured SPO triples and generates 1536-dim embeddings."""
    if not text.strip():
        return []

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # --- PHASE 1: SPO Extraction ---
    response = client.chat.completions.create(
        model="gpt-5.4-mini", # Standardized model name
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract facts from this text:\n\n{text}"}
        ],
        temperature=0.0
    )
    
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```json"):
        raw = raw[7:-3].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
        
    try:
        claims_data = json.loads(raw).get("claims", [])
    except Exception as e:
        logger.error(f"Failed to parse extraction JSON: {e}")
        return []

    # --- PHASE 2: OpenAI Embeddings ---
    if not claims_data:
        return []
        
    texts_to_embed = [
        f"{c.get('subject', '')} {c.get('predicate', '')} {c.get('object', '')}. Context: {c.get('context', '')}"
        for c in claims_data
    ]
    
    emb_response = client.embeddings.create(
        input=texts_to_embed,
        model="text-embedding-3-small"
    )
    
    embeddings = [data.embedding for data in sorted(emb_response.data, key=lambda x: x.index)]
    
    embedded_claims = []
    for claim, emb in zip(claims_data, embeddings):
        embedded_claims.append({
            "claim": claim,
            "embedding": emb
        })
        
    return embedded_claims