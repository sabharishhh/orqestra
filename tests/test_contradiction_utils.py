from services.vector_clock import is_concurrent, increment, merge
from services.lca_computer import compute_lca  # integration test with fixture DB

def test_concurrent_empty_clocks(): assert is_concurrent({}, {}) is True
def test_concurrent_disjoint_keys(): assert is_concurrent({"a": 1}, {"b": 1}) is True
def test_dominance(): assert is_concurrent({"a": 2}, {"a": 1}) is False
def test_equal_clocks_not_concurrent(): assert is_concurrent({"a": 1}, {"a": 1}) is False
def test_increment(): assert increment({"a": 1}, "a") == {"a": 2}
def test_merge_max(): assert merge({"a": 1, "b": 3}, {"a": 5}) == {"a": 5, "b": 3}

# LCA tests require pytest-postgresql or a test fixture DB — sketch the cases:
# - Two claims with shared parent → LCA = parent
# - Two claims with no shared ancestor → LCA = None
# - Deep chains → correct fork distances
# - Depth cap → returns gracefully at MAX_TRAVERSAL_DEPTH