"""
LCA seed-claim demo injector — uses the new parent_claim_id API field.

Demonstrates a Lowest Common Ancestor scenario:
  1. PlannerAgent emits a baseline workout plan (the future LCA)
  2. FitnessAgent derives a recommendation that REFERENCES the planner's claim
  3. MedicalAgent derives a CONTRADICTING recommendation that ALSO references it
  4. The contradiction between FitnessAgent and MedicalAgent now has a real
     shared ancestor (the planner's claim) — provable via /lineage-graph

Usage:
    # Run AFTER inject_traffic_elaborate.py
    python scripts/inject_lca_demo.py
"""
import sys
import time
import secrets
import hashlib
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import System, Organization, Claim


API_URL = "http://localhost:8000"


def get_demo_org_id(db: Session) -> str:
    org = db.query(Organization).filter_by(slug="demo-fitness").first()
    if org is None:
        raise RuntimeError("demo-fitness org not found. Run seed_org first.")
    return org.id


def provision_or_rotate(db: Session, demo_org_id: str, name: str) -> dict:
    """Mint a fresh API key for an agent. Creates the System row if absent."""
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

    return {"id": str(system.id), "key": raw_key}


def post_sample(system_id: str, api_key: str, text: str, agent_name: str,
                parent_claim_id: str = None) -> bool:
    """POST to /systems/{id}/samples, optionally with cross-agent parent pointer."""
    url = f"{API_URL}/systems/{system_id}/samples"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "metadata": {
            "agent_name": agent_name,
            "source": "lca_demo_injector",
        },
        "vector_clock": {system_id: 1},
    }
    if parent_claim_id:
        payload["parent_claim_id"] = parent_claim_id

    response = requests.post(url, json=payload, headers=headers, timeout=10)
    if response.status_code not in (200, 202):
        print(f"   ❌ {agent_name} failed: HTTP {response.status_code} — {response.text[:200]}")
        return False
    return True


def wait_for_planner_claim(db: Session, planner_system_id: str,
                            entity_hint: str = "workout_routine",
                            timeout_seconds: int = 90) -> Claim:
    """Poll until PlannerAgent's seed claim appears in the DB."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        claim = (
            db.query(Claim)
              .filter(
                  Claim.system_id == planner_system_id,
                  Claim.entity_hint == entity_hint,
              )
              .order_by(Claim.extracted_at.desc())
              .first()
        )
        if claim is not None:
            return claim
        time.sleep(2)
    raise TimeoutError(
        f"PlannerAgent's seed claim didn't appear within {timeout_seconds}s. "
        "Check Celery worker logs."
    )


def main():
    parser = argparse.ArgumentParser(description="LCA seed-claim demo injector (uses parent_claim_id API).")
    args = parser.parse_args()

    print("🧬 LCA Seed-Claim Demo Injector (Sprint 6.5)\n")

    db: Session = SessionLocal()
    try:
        demo_org_id = get_demo_org_id(db)
        print(f"🏢 Org: demo-fitness ({demo_org_id})\n")

        # 1) Provision the 3 agents needed for this scenario
        print("📋 Step 1: Provisioning agents...")
        planner = provision_or_rotate(db, demo_org_id, "PlannerAgent")
        fitness = provision_or_rotate(db, demo_org_id, "FitnessAgent")
        medical = provision_or_rotate(db, demo_org_id, "MedicalAgent")

        # 2) POST the seed claim (no parent_claim_id — this is the LCA root)
        print("\n📡 Step 2: PlannerAgent emits the baseline workout plan...")
        seed_text = (
            "User workout plan must include lower-body strength training twice per week. "
            "Lower-body strength training is foundational for the user's fitness goals."
        )
        if not post_sample(planner["id"], planner["key"], seed_text, "PlannerAgent"):
            print("❌ Seed dispatch failed. Aborting.")
            return

        # 3) Wait for the seed claim to materialize through the pipeline
        print("\n⏳ Step 3: Waiting for PlannerAgent's claim to materialize (up to 90s)...")
        try:
            planner_claim = wait_for_planner_claim(db, planner["id"])
        except TimeoutError as e:
            print(f"❌ {e}")
            return
        print(f"   ✅ Seed claim landed: {planner_claim.id}")
        print(f"      \"{planner_claim.subject} {planner_claim.predicate} {planner_claim.object}\"")

        # 4) FitnessAgent derives FROM the planner's claim (parent_claim_id set)
        print("\n📡 Step 4: FitnessAgent derives a heavy-squats recommendation FROM PlannerAgent...")
        fitness_text = (
            "Lower-body strength training should be performed via heavy barbell back squats "
            "with progressive overload, building load week over week."
        )
        if not post_sample(
            fitness["id"], fitness["key"], fitness_text, "FitnessAgent",
            parent_claim_id=str(planner_claim.id),
        ):
            print("❌ FitnessAgent dispatch failed.")
            return
        print(f"   → FitnessAgent claim dispatched (parent={planner_claim.id})")

        # 5) MedicalAgent derives a CONTRADICTING recommendation FROM the same planner claim
        print("\n📡 Step 5: MedicalAgent derives a no-squats override FROM the same PlannerAgent claim...")
        medical_text = (
            "Lower-body strength training must strictly avoid all squat-pattern loading "
            "due to the user's documented knee history requiring patella protection."
        )
        if not post_sample(
            medical["id"], medical["key"], medical_text, "MedicalAgent",
            parent_claim_id=str(planner_claim.id),
        ):
            print("❌ MedicalAgent dispatch failed.")
            return
        print(f"   → MedicalAgent claim dispatched (parent={planner_claim.id})")

        print("\n✅ LCA scenario dispatched.")
        print("\n   Give Celery ~60s to fully process the three claims and detect the contradiction.")
        print("   Then open the dashboard, find the contradiction between FitnessAgent and MedicalAgent")
        print("   about 'lower-body strength training' — its lineage tree should show:")
        print("     • Indigo 'LCA found · fork A:1 / B:1' badge in the header")
        print("     • PlannerAgent claim at depth -1 with indigo/violet top border + Sparkles icon")
        print("     • FitnessAgent and MedicalAgent claims at depth 0 (ROOT, red top border)")
        print("     • Red dashed CONTRADICTION edge between depth-0 claims")

    finally:
        db.close()


if __name__ == "__main__":
    main()