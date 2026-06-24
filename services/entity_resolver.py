"""
Entity hint canonicalization. The extraction LLM emits free-form hints
that drift across runs (meal_plan_selection vs meal_plan_requirements vs
dietary_macros). Without canonicalization, the Level 3 entity-scoped
filter never matches across systems and contradictions are never seen.

Two-stage resolution:
  1. Exact alias lookup against a closed vocabulary
  2. Semantic nearest-neighbor against existing OBG centroids
"""
import logging
import numpy as np
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Closed canonical vocabulary. Add new canonical entities here as new
# domains are onboarded. Aliases are inputs the LLM tends to produce.
CANONICAL_ENTITIES = {
    "workout_schedule":      ["weekly_schedule", "training_days", "rest_days",
                              "weekly_training_plan", "exercise_schedule"],
    "workout_routine":       ["exercises", "exercise_selection", "movement_protocol",
                              "exercise_duration_limit", "workout_exercises",
                              "training_routine"],
    "meal_plan":             ["meal_plan_selection", "meal_plan_requirements",
                              "food_selection", "diet_plan", "nutrition_plan",
                              "monthly_food_selection"],
    "nutrition_macros":      ["dietary_macros", "macro_breakdown", "calorie_target",
                              "calorie_deficit", "calorie_deficit_targets"],
    "sleep_target":          ["sleep_duration", "rest_target", "nighttime_sleep"],
    "activity_limit":        ["session_duration", "exercise_session_limit",
                              "continuous_activity"],
    "food_budget_policy":    ["food_budgeting", "food_selection_policy",
                              "meal_cost_policy", "food_expense_policy",
                              "cost_reduction"],
    "fitness_budget_policy": ["gym_membership", "fitness_budget", "membership_choice",
                              "fitness_expense_policy"],
}

# Inverted alias index for O(1) exact lookup
_ALIAS_INDEX: dict[str, str] = {}
for canon, aliases in CANONICAL_ENTITIES.items():
    _ALIAS_INDEX[canon] = canon
    for alias in aliases:
        _ALIAS_INDEX[alias] = canon

SEMANTIC_MATCH_THRESHOLD = 0.55


def resolve_entity_hint(
    raw_hint: str,
    embedding: Optional[list] = None,
    db: Optional[Session] = None
) -> str:
    """
    Returns canonical entity_hint or normalized raw if no match.
    """
    if not raw_hint:
        return "general"

    normalized = raw_hint.lower().strip().replace(" ", "_").replace("-", "_")

    # Stage 1: exact alias lookup
    if normalized in _ALIAS_INDEX:
        canonical = _ALIAS_INDEX[normalized]
        if canonical != normalized:
            logger.info(f"Entity alias: '{normalized}' → '{canonical}'")
        return canonical

    # Stage 2: semantic nearest-neighbor against existing canonical centroids
    if embedding is not None and db is not None:
        canonical = _semantic_resolve(normalized, embedding, db)
        if canonical:
            return canonical

    # Unknown — return normalized, will accumulate and be picked up by
    # nightly auto-induction for human review.
    logger.info(f"Entity unknown (no canonical match): '{normalized}'")
    return normalized


def _semantic_resolve(normalized: str, embedding: list, db: Session) -> Optional[str]:
    """Find the nearest canonical entity by averaging existing centroids per canonical name."""
    from models.database import EntityBeliefState

    rows = db.query(
        EntityBeliefState.entity_name,
        EntityBeliefState.centroid_embedding
    ).filter(
        EntityBeliefState.entity_name.in_(CANONICAL_ENTITIES.keys()),
        EntityBeliefState.sample_count >= 1
    ).all()

    if not rows:
        return None

    # Aggregate centroids per canonical entity across systems
    canonical_centroids: dict[str, list[np.ndarray]] = {}
    for name, centroid in rows:
        if centroid is None: continue
        canonical_centroids.setdefault(name, []).append(np.array(centroid))

    if not canonical_centroids:
        return None

    emb = np.array(embedding)
    emb_norm = np.linalg.norm(emb)
    if emb_norm == 0:
        return None

    best_canonical = None
    best_similarity = -1.0
    for canonical, centroid_list in canonical_centroids.items():
        mean_centroid = np.mean(centroid_list, axis=0)
        c_norm = np.linalg.norm(mean_centroid)
        if c_norm == 0:
            continue
        sim = float(np.dot(emb, mean_centroid) / (emb_norm * c_norm))
        if sim > best_similarity:
            best_similarity = sim
            best_canonical = canonical

    if best_similarity >= SEMANTIC_MATCH_THRESHOLD:
        logger.info(
            f"Entity semantic resolve: '{normalized}' → '{best_canonical}' "
            f"(sim={best_similarity:.3f})"
        )
        return best_canonical

    return None