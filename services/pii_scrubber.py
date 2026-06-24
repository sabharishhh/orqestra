import re
import logging
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    import spacy
    nlp = spacy.load("en_core_web_sm")

logger = logging.getLogger(__name__)

CLINICAL_ALLOWLIST = {"mg", "ml", "kg", "egfr", "cpt", "icd", "dosage", "blood pressure", "bpm", "dose"}

def scrub_pii(text: str) -> str:
    """F3.4 Compliance: PII scrubber with clinical allowlist and NER."""
    doc = nlp(text)
    scrubbed_text = text
    
    # Simple regex for SSN and Phone
    scrubbed_text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', scrubbed_text)
    scrubbed_text = re.sub(r'\b\d{3}-\d{3}-\d{4}\b', '[REDACTED_PHONE]', scrubbed_text)
    
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE"]:
            # Check if part of the entity is in the clinical allowlist
            if not any(term in ent.text.lower() for term in CLINICAL_ALLOWLIST):
                scrubbed_text = scrubbed_text.replace(ent.text, f"[REDACTED_{ent.label_}]")
                
    return scrubbed_text