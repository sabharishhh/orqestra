"""
Synthetic descendant claim injector — DEMO ONLY.

Creates plausible-looking child claims that reference existing contradictions
via parent_claim_id, so the blast-radius endpoint has data to traverse. In
production, descendants happen naturally when agents reference prior claims;
this script simulates that for the demo data set.

Usage:
    python scripts/inject_synthetic_descendants.py

The script:
  - Picks every open contradiction
  - For each side (claim_a, claim_b), generates 2-3 descendant claims
  - Each descendant references its parent via parent_claim_id
  - Cascades 2 levels deep so blast-radius shows multi-hop propagation
  - Uses plausible entity_hints from the org's canonical vocabulary
"""
import sys
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Make the script importable from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import (
    Claim,
    Contradiction,
    CanonicalEntity,
    Organization,
    System,
)


# Plausible descendant templates per entity_hint. Each tuple is (predicate, object).
# Designed to read naturally as something an agent would actually emit after
# referencing the parent claim. Generic enough to work across the 5 demo orgs.
DESCENDANT_TEMPLATES = {
    "workout_schedule": [
        ("must include",      "morning cardio sessions"),
        ("requires",          "two rest day check-ins per week"),
        ("influences",        "recovery protocol selection"),
    ],
    "workout_routine":  [
        ("requires logging",  "set count and weight per exercise"),
        ("affects",           "weekly intensity targets"),
        ("triggers",          "form check reminders"),
    ],
    "meal_plan": [
        ("must include",      "weekly grocery list generation"),
        ("affects",           "monthly food budget allocation"),
        ("influences",        "supplement recommendations"),
    ],
    "nutrition_macros": [
        ("informs",           "snack-time recommendations"),
        ("triggers",          "shopping list adjustments"),
    ],
    "sleep_target": [
        ("influences",        "evening routine reminders"),
        ("affects",           "morning workout intensity"),
    ],
    "activity_limit": [
        ("requires",          "heart rate monitoring during sessions"),
        ("triggers",          "rest day insertion logic"),
    ],
    "food_budget_policy": [
        ("affects",           "monthly grocery store routing"),
        ("influences",        "premium brand substitutions"),
    ],
    "fitness_budget_policy": [
        ("affects",           "home equipment recommendations"),
        ("influences",        "subscription service choices"),
    ],
}

# Generic fallback for any entity hint not in the table above
GENERIC_TEMPLATES = [
    ("requires further",  "downstream coordination"),
    ("informs",           "related agent decisions"),
    ("affects",           "follow-up recommendations"),
]


def get_templates_for(entity_hint: str) -> list[tuple[str, str]]:
    return DESCENDANT_TEMPLATES.get(entity_hint, GENERIC_TEMPLATES)


def create_descendant(db: Session, parent: Claim, depth: int) -> Claim:
    """Create one synthetic child claim referencing the parent."""
    templates = get_templates_for(parent.entity_hint)
    predicate, obj = random.choice(templates)

    # Reuse the parent's vector_clock with a tick increment to simulate
    # a real causal continuation. Embedding is None — we don't need one
    # since blast-radius doesn't run NLI on synthetic claims.
    new_clock = dict(parent.vector_clock) if parent.vector_clock else {}
    sys_key = str(parent.system_id)
    new_clock[sys_key] = new_clock.get(sys_key, 0) + 1

    descendant = Claim(
        org_id=parent.org_id,
        system_id=parent.system_id,
        entity_hint=parent.entity_hint,
        subject=f"downstream of {parent.subject}",
        predicate=predicate,
        object=obj,
        context=f"synthetic descendant at depth {depth} (demo only)",
        content_hash=f"synth_{parent.content_hash[:12]}_{depth}_{random.randint(1000,9999)}",
        embedding=None,                     # OK — not needed for DAG traversal
        vector_clock=new_clock,
        logical_clock=new_clock[sys_key],
        parent_claim_id=parent.id,          # ← THE KEY FIELD for blast-radius
        parent_hashes=[parent.content_hash] if parent.content_hash else [],
        is_historical=False,
        extracted_at=datetime.now(timezone.utc) + timedelta(minutes=depth),
    )
    db.add(descendant)
    db.flush()
    return descendant


def inject():
    db: Session = SessionLocal()
    try:
        contradictions = db.query(Contradiction).filter_by(status='open').all()
        if not contradictions:
            print("⚠️  No open contradictions found. Run inject_traffic.py first.")
            return

        total_descendants = 0
        for contra in contradictions:
            for side_label, claim_id in [('A', contra.claim_a_id), ('B', contra.claim_b_id)]:
                parent_claim = db.query(Claim).filter_by(id=claim_id).first()
                if parent_claim is None:
                    continue

                # Depth 1: 2-3 children of the root claim
                depth_1_count = random.randint(2, 3)
                depth_1_children = [
                    create_descendant(db, parent_claim, depth=1)
                    for _ in range(depth_1_count)
                ]

                # Depth 2: each depth-1 child gets 1-2 grandchildren
                for child in depth_1_children:
                    depth_2_count = random.randint(1, 2)
                    for _ in range(depth_2_count):
                        create_descendant(db, child, depth=2)
                        total_descendants += 1
                    total_descendants += 1

                print(f"  [{side_label}] contradiction {contra.id} ← {depth_1_count} children + grandchildren synthesized")

        db.commit()
        print(f"\n✅ Synthesized {total_descendants} descendant claims across {len(contradictions)} contradictions.")
        print(f"   Run GET /contradictions/<id>/blast-radius to see the propagation tree.")

    except Exception as e:
        db.rollback()
        print(f"❌ Failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🌱 Injecting synthetic descendants for blast-radius demo...\n")
    inject()