"""
Declare canonical values for the demo-fitness org's fitness entities.

End-to-end validation of the Sprint 8 declare path: creates an ephemeral
CanonAdmin system in the demo-fitness org, uses its API key to hit
POST /canon/declare via HTTP for each fitness entity, then hits
GET /canon/resolve to confirm the value comes back.

Usage:
    docker compose exec api python -m scripts.declare_demo_canon
    docker compose exec api python -m scripts.declare_demo_canon --dry-run

The ephemeral admin system is left in place after the run (cheap; it's
just one row) so /resolve calls from other demo systems continue to
work against the declared values.
"""
import argparse
import hashlib
import logging
import os
import secrets
import sys
from typing import Optional

import requests
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import (
    CanonicalEntity,
    CanonStore,
    Organization,
    System,
    SystemCanonSubscription,
)
from observability import get_logger

logging.basicConfig(level=logging.INFO, format="[declare_demo_canon] %(message)s")
logger = get_logger(__name__)

# --- config ---
DEMO_ORG_SLUG = "demo-fitness"
DEMO_STORE_NAME = "default"
ADMIN_SYSTEM_NAME = "CanonAdmin"

# API base — resolves inside the api container to itself.
API_BASE = os.environ.get("ORQESTRA_API_BASE", "http://localhost:8000")

# --- declarations for the fitness demo ---
# Only names present in the preset (verified in Task 7 prep):
#   activity_limit, meal_plan, nutrition_macros, sleep_target,
#   workout_routine, workout_schedule
DECLARATIONS = [
    {
        "canonical_name": "activity_limit",
        "canonical_value": "no high-impact activity for 6 weeks post-op",
        "canonical_claim_text": "User is 4 weeks post-op ACL repair; no high-impact activity permitted for another 2 weeks.",
    },
    {
        "canonical_name": "workout_schedule",
        "canonical_value": "3 sessions/week, Mon/Wed/Fri, 45 minutes each",
        "canonical_claim_text": "User's workout schedule is 3 sessions per week (Mon/Wed/Fri), 45 minutes per session.",
    },
    {
        "canonical_name": "workout_routine",
        "canonical_value": "upper-body strength + rehab mobility; NO squats, deadlifts, or plyometrics",
        "canonical_claim_text": "Routine is upper-body strength plus rehab mobility work only; squats, deadlifts, and plyometrics excluded due to ACL recovery.",
    },
    {
        "canonical_name": "nutrition_macros",
        "canonical_value": "protein 1.8 g/kg, carbs 3 g/kg, fat 0.9 g/kg",
        "canonical_claim_text": "Daily macro targets: protein 1.8 g per kg body weight, carbs 3 g/kg, fat 0.9 g/kg.",
    },
    {
        "canonical_name": "meal_plan",
        "canonical_value": "4 meals/day, high-protein anti-inflammatory focus",
        "canonical_claim_text": "Four meals per day, high-protein anti-inflammatory focus to support ACL recovery.",
    },
    {
        "canonical_name": "sleep_target",
        "canonical_value": "8 hours/night, in bed by 22:30",
        "canonical_claim_text": "Sleep target is 8 hours per night with bedtime by 22:30 to support recovery.",
    },
]

DECLARED_BY = "demo_operator"


# =====================================================
def get_or_create_admin_system(db: Session, org: Organization, store: CanonStore) -> tuple[System, str]:
    """
    Idempotent admin-system creation. Reuses an existing CanonAdmin row
    if present (its api_key_hash is known); otherwise mints a fresh
    raw token, hashes it, and creates the row.

    Because we never store the raw token, an EXISTING CanonAdmin can't
    be authenticated with. In that case we ROTATE its api_key_hash to
    a freshly-minted raw token, so the script can always run end-to-end.
    """
    raw_token = "oq-" + secrets.token_hex(32)  # 3 + 64 = 67 chars, matches auth.py check
    hashed = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    admin = db.query(System).filter_by(name=ADMIN_SYSTEM_NAME).first()
    if admin:
        # Rotate the hash so THIS run's token is valid.
        admin.api_key_hash = hashed
        # Ensure it belongs to demo-fitness org (guard against drift).
        admin.org_id = org.id
        db.flush()
        logger.info(f"Rotated {ADMIN_SYSTEM_NAME} api_key_hash (id={admin.id})")
    else:
        admin = System(
            org_id=org.id,
            name=ADMIN_SYSTEM_NAME,
            provider="internal",
            description="Ephemeral admin system for scripted Canon declarations.",
            api_key_hash=hashed,
        )
        db.add(admin)
        db.flush()
        logger.info(f"Created {ADMIN_SYSTEM_NAME} system (id={admin.id})")

    # Ensure subscribed to default store at rank 0.
    exists = (
        db.query(SystemCanonSubscription)
          .filter_by(system_id=admin.id, store_id=store.id)
          .first()
    )
    if not exists:
        db.add(SystemCanonSubscription(
            system_id=admin.id,
            store_id=store.id,
            precedence_rank=0,
        ))
        db.flush()
        logger.info(f"Subscribed {ADMIN_SYSTEM_NAME} to default store")

    db.commit()
    return admin, raw_token


def declare_via_http(token: str, store_id: str, canonical_name: str,
                     canonical_value: str, canonical_claim_text: str) -> dict:
    r = requests.post(
        f"{API_BASE}/canon/declare",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "store_id": store_id,
            "canonical_name": canonical_name,
            "canonical_value": canonical_value,
            "canonical_claim_text": canonical_claim_text,
            "declared_by": DECLARED_BY,
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"declare failed for {canonical_name}: HTTP {r.status_code} — {r.text}"
        )
    return r.json()


def resolve_via_http(token: str, entity: str) -> dict:
    r = requests.get(
        f"{API_BASE}/canon/resolve",
        headers={"Authorization": f"Bearer {token}"},
        params={"entity": entity},
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"resolve failed for {entity}: HTTP {r.status_code} — {r.text}"
        )
    return r.json()


def main():
    parser = argparse.ArgumentParser(description="Declare demo-fitness canon values end-to-end.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be declared without hitting the API.")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        if not org:
            logger.error(f"❌ Org '{DEMO_ORG_SLUG}' not found. Run seed_org first.")
            sys.exit(1)

        store = (
            db.query(CanonStore)
              .filter_by(org_id=org.id, name=DEMO_STORE_NAME)
              .first()
        )
        if not store:
            logger.error(f"❌ Store '{DEMO_STORE_NAME}' not found for {DEMO_ORG_SLUG}.")
            sys.exit(1)

        vocab = {
            e.canonical_name
            for e in db.query(CanonicalEntity).filter_by(store_id=store.id).all()
        }
        missing = [d["canonical_name"] for d in DECLARATIONS if d["canonical_name"] not in vocab]
        if missing:
            logger.error(f"❌ Vocabulary missing entities: {missing}")
            logger.error("Re-run seed_org for demo-fitness to seed the consumer preset.")
            sys.exit(1)

        # Extract primitives BEFORE closing the session.
        org_slug = org.slug
        store_id_str = str(store.id)
        store_name = store.name

        if args.dry_run:
            print(f"[dry-run] org={org_slug} store={store_name} ({store_id_str})")
            for d in DECLARATIONS:
                print(f"[dry-run]   declare {d['canonical_name']:24s} = {d['canonical_value']}")
            return

        admin, token = get_or_create_admin_system(db, org, store)
    finally:
        db.close()

    logger.info(f"Using admin token for {ADMIN_SYSTEM_NAME}: {token[:12]}…{token[-6:]}")

    # --- Declare each entity (uses primitives, no ORM objects) ---
    for d in DECLARATIONS:
        result = declare_via_http(
            token=token,
            store_id=store_id_str,
            canonical_name=d["canonical_name"],
            canonical_value=d["canonical_value"],
            canonical_claim_text=d["canonical_claim_text"],
        )
        logger.info(f"✓ declared {d['canonical_name']:24s} → {result['canonical_value']}")

    logger.info("--- verifying via /canon/resolve ---")
    all_good = True
    for d in DECLARATIONS:
        resolved = resolve_via_http(token=token, entity=d["canonical_name"])
        got = resolved.get("canonical_value")
        expected = d["canonical_value"]
        ok = got == expected
        all_good = all_good and ok
        marker = "✓" if ok else "✗"
        logger.info(f"  {marker} {d['canonical_name']:24s}  status={resolved['resolution_status']}  value={got!r}")

    if not all_good:
        logger.error("❌ Some resolve values did not match. Investigate.")
        sys.exit(2)

    logger.info(f"✅ Declared {len(DECLARATIONS)} canonical values in {org_slug}/{store_name}.")


if __name__ == "__main__":
    main()