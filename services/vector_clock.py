def is_concurrent(clock_a: dict, clock_b: dict) -> bool:
    """Two vector clocks are concurrent iff neither dominates the other."""
    if not clock_a or not clock_b: return True
    if clock_a == clock_b: return False
    if not set(clock_a.keys()).intersection(set(clock_b.keys())): return True

    a_leq_b, b_leq_a = True, True
    for k in set(clock_a.keys()).union(set(clock_b.keys())):
        va, vb = clock_a.get(k, 0), clock_b.get(k, 0)
        if va > vb: a_leq_b = False
        if vb > va: b_leq_a = False
    return not (a_leq_b or b_leq_a)

def increment(clock: dict, system_id: str) -> dict:
    new = (clock or {}).copy()
    new[system_id] = new.get(system_id, 0) + 1
    return new

def merge(clock_a: dict, clock_b: dict) -> dict:
    """Element-wise max — used when an agent reads from another's output."""
    keys = set((clock_a or {}).keys()) | set((clock_b or {}).keys())
    return {k: max((clock_a or {}).get(k, 0), (clock_b or {}).get(k, 0)) for k in keys}