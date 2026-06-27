"""
Elaborate Orqestra traffic injector — direct POST mode.

Simulates a realistic 5-agent fitness coaching system over multiple turns.
Each turn each agent emits one narrative block (3-4 claims worth of text)
that references prior claims, producing real parent_claim_id chains for
lineage visualization.

DESIGN NOTE: This script POSTs directly to /systems/{id}/samples with each
agent's API key in the Authorization header, bypassing the Orqestra SDK.
The SDK is a global-state singleton — calling sdk.init() in a loop for
multiple agents creates a race where claims get attributed to whichever
agent was most recently init'd. Bypassing the SDK eliminates that bug
entirely for test/demo scripts. Real customers using the SDK have one
agent per process, so the bug doesn't bite them in production.

Usage:
    python scripts/inject_traffic_elaborate.py                # continuous trickle
    python scripts/inject_traffic_elaborate.py --burst        # no delays
    python scripts/inject_traffic_elaborate.py --turns 3      # custom turn count
"""
import sys
import time
import secrets
import hashlib
import argparse
import random
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import System, Organization


API_URL = "http://localhost:8000"
INGEST_PATH = "/systems/{system_id}/samples"   # NOT /samples/batch — single sample is enough


# =====================================================
# Agent narratives — each turn's block is one POST.
# Turn N's text references entities from turn N-1 so the
# claim extractor naturally produces parent_claim_id chains.
# =====================================================
AGENT_NARRATIVES = {
    "FitnessAgent": [
        # Turn 1
        "Weekly schedule must allocate exactly 6 active workout days and exactly 1 rest day. "
        "Workout routine exercises must include heavy squats and lunges with progressive overload. "
        "Continuous strenuous activity must be limited to 60 minutes per session.",

        # Turn 2 — references Turn 1
        "Following the 6-day weekly schedule, Tuesday and Thursday workouts must include heavy back squats and front squats. "
        "Lunges progression requires adding 5kg per week. "
        "Recovery between heavy leg days requires 48 hours minimum.",

        # Turn 3 — deeper specialization
        "Heavy squats on Tuesday should include 5 sets of 5 reps at 85% one-rep-max. "
        "Walking lunges on Thursday must total 100 reps per session. "
        "Saturday workout requires combined squats and deadlifts within the same session.",
    ],

    "NutritionAgent": [
        "Monthly food selection requires choosing a premium organic meal plan with grass-fed protein sources. "
        "Macro breakdown must maintain a strict calorie deficit of 700 calories per day. "
        "Daily protein target must be 180g distributed across 5 meals.",

        "Premium organic meal plan must source produce from certified local farms within a 100-mile radius. "
        "Calorie deficit of 700 daily requires eliminating all snacks between meals. "
        "Protein distribution requires 36g per meal across the 5-meal structure.",

        "Local organic produce sourcing requires shopping at the farmers market twice per week. "
        "Eliminating snacks requires extending breakfast to include slow-digesting carbs. "
        "Per-meal protein of 36g should come primarily from chicken breast and grass-fed beef.",
    ],

    "MedicalAgent": [
        # Turn 1 — directly contradicts FitnessAgent
        "Workout routine must strictly avoid squats and lunges due to user's documented knee history. "
        "Continuous strenuous activity must be limited to 45 minutes per session to manage cardiovascular strain. "
        "High-impact exercises must be replaced with low-impact alternatives like swimming and cycling.",

        "Low-impact alternatives must include swimming for 30 minutes and cycling for 20 minutes per session. "
        "Knee-sparing protocols require avoiding any exercise that loads the patella beyond bodyweight. "
        "Cardiovascular strain limit of 45 minutes requires heart rate monitoring at 65% max heart rate ceiling.",

        "Swimming sessions must be performed at moderate pace to keep heart rate below 65% max. "
        "Cycling must use a recumbent bike to further reduce knee loading. "
        "Patella-protection protocol requires zero weighted leg exercises until cleared by orthopedic followup.",
    ],

    "RecoveryAgent": [
        # Turn 1 — contradicts FitnessAgent on schedule
        "Weekly schedule must allocate exactly 5 active workout days and exactly 2 rest days for proper recovery. "
        "Nighttime sleep target must be at least 8 hours per night. "
        "Active recovery on rest days requires light walking for 30 minutes.",

        "The 2 rest days must be split as 1 mid-week and 1 weekend to optimize muscle protein synthesis. "
        "Sleep target of 8 hours requires going to bed by 10pm based on a 6am wake schedule. "
        "Light walking on rest days must avoid any incline to keep heart rate at recovery zone.",

        "Mid-week rest day must fall on Wednesday to break up the training week. "
        "10pm bedtime requires eliminating blue light exposure after 9pm. "
        "Recovery zone walking should keep heart rate below 60% max for the full 30 minutes.",
    ],

    "BudgetAgent": [
        # Turn 1 — contradicts NutritionAgent + FitnessAgent
        "Monthly food selection requires eliminating premium organic meal plans to lower expenses. "
        "Gym membership selection must focus on home workouts to reduce monthly fitness costs. "
        "Equipment purchases should prioritize used or refurbished items under 200 dollars total.",

        "Eliminating organic meal plans should redirect savings toward bulk-buying conventional staples. "
        "Home workout setup requires bodyweight-only programming for the first 3 months. "
        "Refurbished equipment budget should be split between resistance bands and a single adjustable kettlebell.",

        "Bulk-buying conventional staples requires monthly trips to warehouse club stores. "
        "Bodyweight-only programming must include push-ups, pull-ups, and bodyweight squats as core movements. "
        "Resistance bands purchase should prioritize the 5-band loop set under 30 dollars.",
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
    Mint a fresh API key for each agent. Returns {name: {id, key}} mapping.
    Reuses existing System rows so historical claims persist across runs.
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


def post_sample(system_id: str, api_key: str, text: str, turn: int, agent_name: str):
    """
    Direct POST to /systems/{id}/samples. No SDK, no globals, no batching.
    Each call is fully self-contained — the API key in the header authenticates
    the exact agent we mean.
    """
    url = f"{API_URL}{INGEST_PATH.format(system_id=system_id)}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "metadata": {
            "agent_name": agent_name,
            "turn": turn,
            "source": "elaborate_injector",
        },
        "vector_clock": {system_id: turn},
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    if response.status_code not in (200, 202):
        print(f"   ❌ {agent_name} turn {turn} failed: HTTP {response.status_code} — {response.text[:200]}")
        return False
    return True


def dispatch_turn(turn_index: int, agent_credentials: dict, burst: bool):
    """Send one turn's worth of narrative for every agent."""
    print(f"\n📡 Turn {turn_index + 1}: dispatching for all 5 agents")

    agents = list(AGENT_NARRATIVES.items())
    random.shuffle(agents)

    for name, narratives in agents:
        if turn_index >= len(narratives):
            continue

        text = narratives[turn_index]
        creds = agent_credentials[name]

        ok = post_sample(
            system_id=creds["id"],
            api_key=creds["key"],
            text=text,
            turn=turn_index + 1,
            agent_name=name,
        )
        if ok:
            print(f"   → {name} turn {turn_index + 1} dispatched ({len(text)} chars)")

        if not burst:
            time.sleep(1.5)


def main():
    parser = argparse.ArgumentParser(description="Elaborate Orqestra traffic injector (SDK-bypass mode).")
    parser.add_argument("--burst", action="store_true", help="No delays between dispatches.")
    parser.add_argument("--turns", type=int, default=3, help="Number of turns to run (max 3).")
    args = parser.parse_args()

    if args.turns > 3:
        print("⚠️  Narratives only support up to 3 turns. Capping at 3.")
        args.turns = 3

    print("🚀 Elaborate Orqestra Traffic Simulator (direct-POST mode)")
    print(f"   Mode: {'BURST' if args.burst else 'CONTINUOUS TRICKLE'}")
    print(f"   Turns: {args.turns}")
    print(f"   Expected claims: ~{5 * args.turns * 3} (5 agents × {args.turns} turns × ~3 claims/turn)")

    db: Session = SessionLocal()
    try:
        demo_org_id = get_demo_org_id(db)
        print(f"\n🏢 Scoping agents to org: demo-fitness ({demo_org_id})")
        agent_credentials = provision_agents(db, demo_org_id)
    finally:
        db.close()

    for turn_index in range(args.turns):
        dispatch_turn(turn_index, agent_credentials, args.burst)

        if not args.burst and turn_index < args.turns - 1:
            print(f"   ⏸  Pausing 12s for Celery to process turn batch...")
            time.sleep(12)

    print("\n📡 All turns dispatched.")
    if args.burst:
        print("   Give Celery ~60s to fully process the pipeline.")
    else:
        print("   Pipeline processing should complete within a minute.")


if __name__ == "__main__":
    main()