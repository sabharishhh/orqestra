import time
import secrets
import hashlib
import sdk as orqestra
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import System, Organization
from healthtrack.knowledge_bases import FITNESS_KB, NUTRITION_KB, MEDICAL_KB, RECOVERY_KB, BUDGET_KB

API_URL = "http://localhost:8000"

agents = {
    "FitnessAgent": FITNESS_KB,
    "NutritionAgent": NUTRITION_KB,
    "MedicalAgent": MEDICAL_KB,
    "RecoveryAgent": RECOVERY_KB,
    "BudgetAgent": BUDGET_KB,
}

print("🚀 Booting Live Traffic Simulator & Cryptographic Seeder...")
db: Session = SessionLocal()

# Sprint 3.2: resolve tenant scope. The auto-seed on API startup created
# this org; we just look it up and attach all demo agents to it.
org = db.query(Organization).filter_by(slug="demo-fitness").first()
if org is None:
    db.close()
    raise RuntimeError(
        "demo-fitness org not found. Start the API container so it auto-seeds, "
        "or run: docker compose exec api python -m scripts.seed_org "
        "--name 'Demo Fitness' --slug demo-fitness --preset consumer"
    )
demo_org_id = org.id
print(f"🏢 Scoping agents to org: demo-fitness ({demo_org_id})")

agent_credentials = {}
for name, text in agents.items():
    # 1. Generate F7.3 Compliant Key (oq- + 64 hex chars)
    raw_key = f"oq-{secrets.token_hex(32)}"
    key_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    system = db.query(System).filter_by(name=name).first()
    if not system:
        # 2. Securely provision the agent directly in the DB
        system = System(
            org_id=demo_org_id,
            name=name,
            provider="openai",
            api_key_hash=key_hash,
        )
        db.add(system)
        db.commit()
        db.refresh(system)
        print(f"✅ Provisioned New Agent: {name} -> {system.id}")
    else:
        # 3. Rotate key for existing system so the simulator always works
        system.api_key_hash = key_hash
        # Defensive: backfill org_id if a pre-migration row exists
        if system.org_id is None:
            system.org_id = demo_org_id
        db.commit()
        print(f"🔄 Reconnected & Rotated Key for: {name} -> {system.id}")

    agent_credentials[name] = {
        "id": str(system.id),
        "key": raw_key,
        "text": text,
    }

db.close()

for name, data in agent_credentials.items():
    # Initialize the Orqestra SDK using the newly minted, compliant API key
    orqestra.init(system_id=data["id"], orqestra_api_key=data["key"], orqestra_url=API_URL)
    # Vector clock dynamically tracks the agent's exact UUID
    orqestra.on_write(
        text=data["text"],
        metadata={"agent_name": name},
        vector_clock={data["id"]: 1},
    )
    time.sleep(0.5)

print("📡 Secure Telemetry dispatched! Waiting for Celery to process...")
time.sleep(2)