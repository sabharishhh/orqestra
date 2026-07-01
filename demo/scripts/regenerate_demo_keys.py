"""One-shot: regenerate API keys for the 5 demo agents.

Updates api_key_hash in the DB for each agent and prints the raw keys
ONCE to stdout. Save the output immediately — the raw keys can't be
recovered after this runs.

Usage:
  docker compose exec api python demo/scripts/regenerate_demo_keys.py
"""

import hashlib
import secrets
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import System, Organization

AGENT_NAMES = [
    "FitnessAgent",
    "MedicalAgent",
    "NutritionAgent",
    "RecoveryAgent",
    "BudgetAgent",
]
ORG_SLUG = "demo-fitness"


def main() -> int:
    db: Session = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=ORG_SLUG).first()
        if org is None:
            print(f"ERROR: org slug '{ORG_SLUG}' not found", file=sys.stderr)
            return 1

        print("# Save these keys to demo/.env.demo IMMEDIATELY.")
        print("# Raw keys cannot be recovered after this script exits.")
        print()
        print("ORQESTRA_API=http://api:8000")
        print()

        for name in AGENT_NAMES:
            system = (
                db.query(System)
                .filter_by(org_id=org.id, name=name)
                .first()
            )
            if system is None:
                print(f"# WARN: {name} not found in org {ORG_SLUG}", file=sys.stderr)
                continue

            raw_key = f"oq-{secrets.token_hex(32)}"
            new_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            system.api_key_hash = new_hash
            db.add(system)

            upper = name.upper().replace("AGENT", "_AGENT")
            print(f"{upper}_SYSTEM_ID={system.id}")
            print(f"{upper}_KEY={raw_key}")
            print()

        db.commit()
        print("# Keys committed to DB. Demo agents can now authenticate.", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())