import os
import json
import logging
from typing import List, Dict, Any
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a precise operational data extraction engine.
Your task is to decompose raw text into an explicit array of factual claims represented as Subject-Predicate-Object (SPO) triples with a strict contextual modifier.

Return ONLY JSON matching:
{
  "claims": [
    {
      "subject": "string",
      "predicate": "string",
      "object": "string",
      "context": "string"
    }
  ]
}"""

@retry(wait=wait_exponential(multiplier=2, min=2, max=10), stop=stop_after_attempt(3), reraise=True)
def run_extraction(text: str) -> List[Dict[str, Any]]:
    """Worker 1 Phase: Extracts structured SPO triples and generates 1536-dim embeddings."""
    if not text.strip():
        return []

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # --- PHASE 1: SPO Extraction ---
    response = client.chat.completions.create(
        model="gpt-4o-mini",
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