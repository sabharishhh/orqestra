import re
import logging

logger = logging.getLogger(__name__)

# F3.4 Compliance: Clinical Allowlist Patterns
CLINICAL_PATTERNS = [
    r'\beGFR:\s*\d+\s*mL/min\b',          # eGFR scores
    r'\bCPT:\s*\d{5}\b',                  # CPT codes
    r'\bICD-10:\s*[A-Z][0-9]{2}\.[0-9]{1,2}\b', # ICD-10 codes
    r'\b\d{2,3}/\d{2,3}\s*(?:mmHg)?\b',   # Blood pressure (e.g., 120/80)
    r'\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|IU)\b' # Drug dosages
]

def scrub_pii(text: str) -> str:
    """Strips PHI/PII while strictly preserving clinical allowlist values."""
    if not text:
        return ""
        
    # Step 1: Mask allowed clinical values
    safelist_map = {}
    for i, pattern in enumerate(CLINICAL_PATTERNS):
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for match in matches:
            placeholder = f"__CLINICAL_SAFE_{len(safelist_map)}__"
            safelist_map[placeholder] = match
            text = text.replace(match, placeholder)

    # Step 2: Scrub actual PII
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', text)
    text = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w{2,4}\b', '[REDACTED_EMAIL]', text)
    text = re.sub(r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b', '[REDACTED_PHONE]', text)
    text = re.sub(r'\b[A-Z]{2,3}-\d{6,8}\b', '[REDACTED_MRN]', text)

    # Step 3: Restore clinical values
    for placeholder, original_value in safelist_map.items():
        text = text.replace(placeholder, original_value)
        
    return text