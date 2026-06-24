# F2.3: Per-entity-category cosine thresholds
COSINE_THRESHOLDS = {
    "clinical":     {"level_0": 0.25, "level_3": 0.30},   # Tighter — false positives are costly
    "compliance":   {"level_0": 0.25, "level_3": 0.30},
    "pricing":      {"level_0": 0.30, "level_3": 0.35},
    "policy":       {"level_0": 0.35, "level_3": 0.40},
    "consumer":     {"level_0": 0.40, "level_3": 0.45},   # Looser — paraphrase tolerance
    "general":      {"level_0": 0.35, "level_3": 0.40},
}

# Map entity_hint → category
ENTITY_CATEGORY = {
    "workout_schedule": "consumer", "workout_routine": "consumer",
    "meal_plan": "consumer", "sleep_target": "consumer",
    "activity_limit": "clinical",  # medical-adjacent
    # ... extend
}

def get_thresholds(entity_hint: str) -> dict:
    category = ENTITY_CATEGORY.get(entity_hint, "general")
    return COSINE_THRESHOLDS[category]

# F1.5: high-variance bypass
HIGH_VARIANCE_THRESHOLD = 0.40

def should_bypass_level_0(belief_variance: float) -> bool:
    """F1.5: if internal variance > 0.40, the centroid is unreliable —
    bypass Level 0 and let Level 3 + 4 decide on a claim-pair basis."""
    return belief_variance > HIGH_VARIANCE_THRESHOLD