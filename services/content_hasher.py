import re
import hashlib

HEDGE_WORDS = [
    r"\bi think\b", r"\bi believe\b", r"\bmaybe\b", r"\bprobably\b",
    r"\bmight be\b", r"\bpossibly\b", r"\bperhaps\b", r"\busually\b",
    r"\bmostly\b", r"\bkind of\b", r"\bsort of\b"
]
HEDGE_PATTERN = re.compile("|".join(HEDGE_WORDS), flags=re.IGNORECASE)

def normalize_and_hash(subject: str, predicate: str, obj: str) -> str:
    """Creates a deterministic semantic fingerprint by stripping noise."""
    raw = f"{subject} {predicate} {obj}".lower()
    
    # Remove hedge words
    raw = HEDGE_PATTERN.sub("", raw)
    
    # Remove terminal punctuation (.,;!?)
    raw = re.sub(r'[.,;!?]+$', '', raw.strip())
    
    # Collapse multiple whitespaces into a single space
    raw = re.sub(r'\s+', ' ', raw).strip()
    
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()