import json
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
from openai import OpenAI
from output_collector import SystemConfig, RETRYABLE_EXCEPTIONS
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

# ==========================================
# DATA STRUCTURES
# ==========================================

@dataclass
class ExtractedClaim:
    subject: str
    predicate: str
    obj: str  # 'object' is a reserved word in Python
    context: str

# ==========================================
# EXTRACTION PROMPT
# ==========================================

EXTRACTION_SYSTEM_PROMPT = """You are a precise clinical and operational data extraction engine.
Your task is to decompose raw text from a medical/insurance AI agent into an explicit array of factual claims represented as Subject-Predicate-Object (SPO) triples with a strict contextual modifier.

For every distinct claim or rule stated in the text, extract:
1. subject: The entity, drug, condition, or policy item being discussed (e.g., "Metformin", "Prior Authorization").
2. predicate: The relationship, requirement, or state (e.g., "requires", "is contraindicated with", "has a limit of").
3. object: The value, target, or condition associated with the predicate (e.g., "Step Therapy", "eGFR < 30", "30 days").
4. context: Any temporal bounds, specific patient sub-populations, or qualifying criteria (e.g., "for Type 2 Diabetes", "within 12 months", "none").

CRITICAL: Return your response ONLY as a valid JSON object matching this schema. Do not wrap it in markdown code blocks or add any conversational text.

Schema:
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

# ==========================================
# JSON REPAIR LAYER (Rule 6: Never Crash)
# ==========================================

def clean_markdown_and_whitespace(raw_text: str) -> str:
    """Removes leading/trailing markdown blocks and whitespace noise."""
    text = raw_text.strip()
    # Strip opening markdown fence
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    # Strip closing markdown fence
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

def attempt_regex_repair(raw_text: str) -> List[Dict[str, Any]]:
    """
    If direct JSON parsing fails, uses regex to salvage individual 
    SPO JSON blocks embedded within a malformed string structure.
    """
    claims = []
    # Match structural blocks resembling an object with subject, predicate, object fields
    pattern = r'\{\s*"subject"\s*:\s*"(.*?)"\s*,\s*"predicate"\s*:\s*"(.*?)"\s*,\s*"object"\s*:\s*"(.*?)"\s*,\s*"context"\s*:\s*"(.*?)"\s*\}'
    matches = re.findall(pattern, raw_text, re.DOTALL)
    
    for match in matches:
        try:
            claims.append({
                "subject": match[0].strip(),
                "predicate": match[1].strip(),
                "object": match[2].strip(),
                "context": match[3].strip()
            })
        except Exception:
            continue
            
    return claims

def parse_extraction_response(raw_response: str) -> List[ExtractedClaim]:
    """
    Parses the LLM output into a list of ExtractedClaim objects.
    Guaranteed never to crash; defaults to returning [] on critical failures.
    """
    cleaned_text = clean_markdown_and_whitespace(raw_response)
    parsed_claims_data = []

    # Strategy 1: Standard JSON Parse
    try:
        data = json.loads(cleaned_text)
        if isinstance(data, dict) and "claims" in data:
            parsed_claims_data = data["claims"]
        elif isinstance(data, list):
            parsed_claims_data = data
    except json.JSONDecodeError:
        logger.warning("Primary JSON decoding failed. Initiating Strategy 2 (Regex Repair).")
        # Strategy 2: Regex Fallback Repair
        try:
            parsed_claims_data = attempt_regex_repair(cleaned_text)
        except Exception as e:
            logger.error(f"Regex repair completely failed: {e}")
            return []

    # Final conversion and structural sanitization
    validated_claims = []
    for item in parsed_claims_data:
        try:
            if not isinstance(item, dict):
                continue
            
            # Remap fields safely while guaranteeing fallback defaults
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj_val = str(item.get("object", "")).strip()
            context = str(item.get("context", "none")).strip()

            if subject and predicate and obj_val:
                validated_claims.append(ExtractedClaim(
                    subject=subject,
                    predicate=predicate,
                    obj=obj_val,
                    context=context
                ))
        except Exception as item_err:
            logger.debug(f"Skipping unparseable claim row: {item_err}")
            continue

    return validated_claims

# ==========================================
# CORE EXTRACTION RUNNER
# ==========================================

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=4),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
def extract_claims(text_content: str, config: SystemConfig) -> List[ExtractedClaim]:
    """
    Executes claim extraction using the configured OpenAI system.
    Defaults to the newly assigned gpt-5.4-mini engine variant.
    """
    if not text_content.strip():
        return []

    client_kwargs = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    client = OpenAI(**client_kwargs)
    
    try:
        response = client.chat.completions.create(
            model=config.model if config.model else "gpt-5.4-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract facts from this agent statement:\n\n{text_content}"}
            ],
            temperature=0.0  # Guardrail for strict structured generation consistency
        )
        raw_output = response.choices[0].message.content or ""
        return parse_extraction_response(raw_output)
        
    except Exception as e:
        logger.error(f"Failed execution during extract_claims API invocation: {e}")
        # Ensure that even unexpected upstream network crashes return [] to keep pipeline intact
        return []