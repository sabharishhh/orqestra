import time
import httpx
import sdk as orqestra
from healthtrack.knowledge_bases import FITNESS_KB, NUTRITION_KB, MEDICAL_KB, RECOVERY_KB, BUDGET_KB

API_URL = "http://localhost:8000"
HEADERS = {"X-Orqestra-Key": "dev-test-key"}

agents = {
    "FitnessAgent": FITNESS_KB,
    "NutritionAgent": NUTRITION_KB,
    "MedicalAgent": MEDICAL_KB,
    "RecoveryAgent": RECOVERY_KB,
    "BudgetAgent": BUDGET_KB
}

print("🚀 Booting Live Traffic Simulator...")

# Fetch existing systems to prevent 'already registered' errors
try:
    existing_resp = httpx.get(f"{API_URL}/systems/")
    existing_systems = {s["name"]: s["id"] for s in existing_resp.json()}
except Exception as e:
    print(f"Failed to connect to FastAPI: {e}")
    exit(1)

for name, text in agents.items():
    sys_id = existing_systems.get(name)
    
    if not sys_id:
        resp = httpx.post(f"{API_URL}/systems/", json={"name": name, "provider": "openai"}, headers=HEADERS)
        if resp.status_code == 200:
            sys_id = resp.json()["id"]
            print(f"✅ Registered New Agent: {name} -> {sys_id}")
        else:
            print(f"⚠️ Failed to register {name}: {resp.text}")
            continue
    else:
        print(f"🔄 Reconnected Existing Agent: {name} -> {sys_id}")

    # Initialize the Orqestra SDK for this specific agent
    orqestra.init(system_id=sys_id, orqestra_api_key="dev-test-key", orqestra_url=API_URL)
    
    # --- THE CLEAN SDK IMPLEMENTATION ---
    # vector_clock is now passed explicitly as a top-level parameter,
    # proving to Level 1 that these are independent, concurrent timelines!
    orqestra.on_write(
        text=text, 
        metadata={"agent_name": name},
        vector_clock={sys_id: 1}  
    )
    
    # Small stagger to simulate real-world asynchronous traffic
    time.sleep(0.5) 

print("📡 Telemetry dispatched to background queues! Waiting for Celery to process...")
time.sleep(2) # Give the background thread time to flush