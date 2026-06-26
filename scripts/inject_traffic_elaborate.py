"""
Elaborate Orqestra traffic injector.

Simulates a realistic 5-agent fitness coaching system over multiple turns.
Each agent emits claims that reference its own prior claims (real
parent_claim_id chains, not synthetic), and contradictions emerge naturally
across multi-level lineages — perfect for blast-radius and lineage demos.

Usage:
    # Continuous trickle (default — ~3 min total runtime)
    python scripts/inject_traffic_elaborate.py

    # Burst mode (no sleeps, ~30 seconds total)
    python scripts/inject_traffic_elaborate.py --burst

    # Custom turn count
    python scripts/inject_traffic_elaborate.py --turns 5

Design:
    - 5 agents: Fitness, Nutrition, Medical, Recovery, Budget
    - 3 turns by default. Each turn each agent emits 3-4 claims.
    - Claims within an agent reference prior claims via parent_claim_id.
    - Contradictions designed at different depths so lineage trees are deep.

After running:
    - Run blast-radius on any contradiction to see multi-level propagation.
    - Open the dashboard and click "View Lineage" — tree should be 3-5 levels.
"""
import sys
import time
import secrets
import hashlib
import argparse
import random
from pathlib import Path
from typing import Optional

# Make script importable from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sdk as orqestra
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import System, Organization, Claim


API_URL = "http://localhost:8000"


# =====================================================
# AGENT NARRATIVES — multi-turn scripts per agent
# Each turn's text is one POST to the API. The agent's
# claims naturally evolve and reference prior decisions.
# Contradictions emerge between agents at varying depths.
# =====================================================
AGENT_NARRATIVES = {
    "FitnessAgent": [
        # Turn 1 — foundational
        "Weekly schedule must allocate exactly 6 active workout days and exactly 1 rest day. "
        "Workout routine exercises must include heavy squats and lunges with progressive overload. "
        "Continuous strenuous activity must be limited to 60 minutes per session.",

        # Turn 2 — refines based on Turn 1
        "Following the 6-day weekly schedule, Tuesday and Thursday workouts must include heavy back squats and front squats. "
        "Lunges progression requires adding 5kg per week. "
        "Recovery between heavy leg days requires 48 hours minimum.",

        # Turn 3 — further specialization
        "Heavy squats on Tuesday should include 5 sets of 5 reps at 85% one-rep-max. "
        "Walking lunges on Thursday must total 100 reps per session. "
        "Saturday workout requires combined squats and deadlifts within the same session.",
    ],

    "NutritionAgent": [
        # Turn 1
        "Monthly food selection requires choosing a premium organic meal plan with grass-fed protein sources. "
        "Macro breakdown must maintain a strict calorie deficit of 700 calories per day. "
        "Daily protein target must be 180g distributed across 5 meals.",

        # Turn 2
        "Premium organic meal plan must source produce from certified local farms within a 100-mile radius. "
        "Calorie deficit of 700 daily requires eliminating all snacks between meals. "
        "Protein distribution requires 36g per meal across the 5-meal structure.",

        # Turn 3
        "Local organic produce sourcing requires shopping at the farmers market twice per week. "
        "Eliminating snacks requires extending breakfast to include slow-digesting carbs. "
        "Per-meal protein of 36g should come primarily from chicken breast and grass-fed beef.",
    ],

    "MedicalAgent": [
        # Turn 1 — directly contradicts FitnessAgent on exercise selection
        "Workout routine must strictly avoid squats and lunges due to user's documented knee history. "
        "Continuous strenuous activity must be limited to 45 minutes per session to manage cardiovascular strain. "
        "High-impact exercises must be replaced with low-impact alternatives like swimming and cycling.",

        # Turn 2 — refines medical guidance
        "Low-impact alternatives must include swimming for 30 minutes and cycling for 20 minutes per session. "
        "Knee-sparing protocols require avoiding any exercise that loads the patella beyond bodyweight. "
        "Cardiovascular strain limit of 45 minutes requires heart rate monitoring at 65% max heart rate ceiling.",

        # Turn 3 — even deeper restrictions
        "Swimming sessions must be performed at moderate pace to keep heart rate below 65% max. "
        "Cycling must use a recumbent bike to further reduce knee loading. "
        "Patella-protection protocol requires zero weighted leg exercises until cleared by orthopedic followup.",
    ],

    "RecoveryAgent": [
        # Turn 1 — contradicts FitnessAgent on schedule
        "Weekly schedule must allocate exactly 5 active workout days and exactly 2 rest days for proper recovery. "
        "Nighttime sleep target must be at least 8 hours per night. "
        "Active recovery on rest days requires light walking for 30 minutes.",

        # Turn 2
        "The 2 rest days must be split as 1 mid-week and 1 weekend to optimize muscle protein synthesis. "
        "Sleep target of 8 hours requires going to bed by 10pm based on a 6am wake schedule. "
        "Light walking on rest days must avoid any incline to keep heart rate at recovery zone.",

        # Turn 3
        "Mid-week rest day must fall on Wednesday to break up the training week. "
        "10pm bedtime requires eliminating blue light exposure after 9pm. "
        "Recovery zone walking should keep heart rate below 60% max for the full 30 minutes.",
    ],

    "BudgetAgent": [
        # Turn 1 — contradicts NutritionAgent on meal plan + FitnessAgent on gym
        "Monthly food selection requires eliminating premium organic meal plans to lower expenses. "
        "Gym membership selection must focus on home workouts to reduce monthly fitness costs. "
        "Equipment purchases should prioritize used or refurbished items under $200 total.",

        # Turn 2
        "Eliminating organic meal plans should redirect savings toward bulk-buying conventional staples. "
        "Home workout setup requires bodyweight-only programming for the first 3 months. "
        "Refurbished equipment budget should be split between resistance bands and a single adjustable kettlebell.",

        # Turn 3
        "Bulk-buying conventional staples requires monthly trips to warehouse club stores. "
        "Bodyweight-only programming must include push-ups, pull-ups, and bodyweight squats as core movements. "
        "Resistance bands purchase should prioritize the 5-band loop set under $30.",
    ],
}


def get_demo_org_id(db: Session) -> str:
    org = db.query(Organization).filter_by(slug="demo-fitness").first()
    if org is None:
        raise RuntimeError(
            "demo-fitness org not found. Start the API container so auto-seed runs, "
            "or run: docker compose exec api python -m scripts.seed_org "
            "--name 'Demo Fitness' --slug demo-fitness --preset consumer"
        )
    return org.id


def provision_agents(db: Session, demo_org_id: str) -> dict:
    """
    Mint fresh API keys for each agent. Reuses existing rows so claim
    history accumulates across runs (you can see lineage build up).
    """
    agent_credentials = {}
    for name in AGENT_NARRATIVES.keys():
        raw_key = f"oq-{secrets.token_hex(32)}"
        key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

        system = db.query(System).filter_by(name=name).first()
        if not system:
            system = System(
                org_id=demo_org_id,
                name=name,
                provider="openai",
                api_key_hash=key_hash,
            )
            db.add(system)
            db.commit()
            db.refresh(system)
            print(f"  ✅ Provisioned {name} → {system.id}")
        else:
            system.api_key_hash = key_hash
            if system.org_id is None:
                system.org_id = demo_org_id
            db.commit()
            print(f"  🔄 Rotated key for {name} → {system.id}")

        agent_credentials[name] = {
            "id": str(system.id),
            "key": raw_key,
        }
    return agent_credentials


def dispatch_turn(
    turn_index: int,
    agent_credentials: dict,
    burst: bool,
):
    """Send one turn's worth of claims for every agent."""
    print(f"\n📡 Turn {turn_index + 1}: dispatching claims for all 5 agents")

    # Randomize agent order so contradictions don't always fire in the same order
    agents = list(AGENT_NARRATIVES.items())
    random.shuffle(agents)

    for name, narratives in agents:
        if turn_index >= len(narratives):
            continue

        text = narratives[turn_index]
        creds = agent_credentials[name]

        # Initialize SDK for this agent (re-init each call — SDK is global-state safe in burst)
        orqestra.init(
            system_id=creds["id"],
            orqestra_api_key=creds["key"],
            orqestra_url=API_URL,
        )

        # Vector clock advances per turn so the system records logical time
        orqestra.on_write(
            text=text,
            metadata={"agent_name": name, "turn": turn_index + 1, "source": "elaborate_injector"},
            vector_clock={creds["id"]: turn_index + 1},
        )
        print(f"   → {name} turn {turn_index + 1} dispatched ({len(text)} chars)")

        if not burst:
            # Trickle: small delay between agents so the dashboard sees them arrive in sequence
            time.sleep(1.5)


def main():
    parser = argparse.ArgumentParser(description="Elaborate Orqestra traffic injector.")
    parser.add_argument(
        "--burst",
        action="store_true",
        help="No delays — useful for fast testing. Default is continuous trickle.",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=3,
        help="Number of turns to run (default 3, max 3 with current narratives).",
    )
    args = parser.parse_args()

    if args.turns > 3:
        print("⚠️  Narratives only support up to 3 turns. Capping at 3.")
        args.turns = 3

    print("🚀 Elaborate Orqestra Traffic Simulator")
    print(f"   Mode: {'BURST' if args.burst else 'CONTINUOUS TRICKLE'}")
    print(f"   Turns: {args.turns}")
    print(f"   Expected claims: {5 * args.turns * 3} approx (5 agents × {args.turns} turns × ~3 claims/turn)")

    # Bootstrap
    db: Session = SessionLocal()
    try:
        demo_org_id = get_demo_org_id(db)
        print(f"\n🏢 Scoping agents to org: demo-fitness ({demo_org_id})")
        agent_credentials = provision_agents(db, demo_org_id)
    finally:
        db.close()

    # Run the turns
    for turn_index in range(args.turns):
        dispatch_turn(turn_index, agent_credentials, args.burst)

        if not args.burst and turn_index < args.turns - 1:
            # Pause between turns so Celery can process each batch fully
            # before the next wave arrives — gives clean per-turn contradiction signals
            print(f"   ⏸  Pausing 12s between turns for processing...")
            time.sleep(12)

    print("\n📡 All turns dispatched.")
    if args.burst:
        print("   In burst mode — give Celery ~30s to fully process the pipeline.")
        print("   Then check: SELECT severity, cost_usd FROM contradictions;")
    else:
        print("   Pipeline processing should complete within a minute.")
        print("   Check the dashboard or run blast-radius queries.")


if __name__ == "__main__":
    main()