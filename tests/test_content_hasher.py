import pytest
from services.content_hasher import normalize_and_hash

PARAPHRASE_PAIRS = [
    # Each tuple: (subject, predicate, object) variations that MUST hash identically
    (("Returns", "are accepted within", "30 days"),
     ("returns", "accepted within", "30 days.")),
    (("I think the policy", "is", "30 days"),
     ("policy", "is", "30 days")),
    (("Maybe the refund", "takes", "5 business days"),
     ("the refund", "takes", "5 business days")),
    # ... 50 pairs total covering:
    #   - hedge words (i think, maybe, probably, possibly)
    #   - terminal punctuation (. , ; !)
    #   - whitespace collapse (multiple spaces, tabs)
    #   - case variation
    #   - article noise (the, a, an)
    #   - domain-specific paraphrases (clinical, financial, policy)
]

@pytest.mark.parametrize("a,b", PARAPHRASE_PAIRS)
def test_paraphrase_hash_equality(a, b):
    """F1.2 spec: semantically identical claims must produce identical hashes."""
    hash_a = normalize_and_hash(*a)
    hash_b = normalize_and_hash(*b)
    assert hash_a == hash_b, f"Paraphrase hash mismatch:\n  A: {a}\n  B: {b}"

DISTINCT_PAIRS = [
    (("Returns", "are accepted within", "30 days"),
     ("Returns", "are accepted within", "15 days")),  # different value
    (("Returns", "are accepted within", "30 days"),
     ("Refunds", "are accepted within", "30 days")),  # different subject
    # ... 20 pairs of genuinely-different claims that MUST hash differently
]

@pytest.mark.parametrize("a,b", DISTINCT_PAIRS)
def test_distinct_hash_inequality(a, b):
    """Distinct claims must NOT collide."""
    assert normalize_and_hash(*a) != normalize_and_hash(*b)