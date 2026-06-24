import os, uuid, logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from core.celery_app import celery_app
from core.database import SessionLocal
from models.database import System, Claim, Contradiction

logger = logging.getLogger(__name__)

# Known-good canary pairs (must be detected; if missed, detection is broken)
CANARY_PAIRS = [
    {
        "id": "CANARY-001",
        "system_a_name": "CanarySystemA",
        "system_b_name": "CanarySystemB",
        "claim_a": {"subject": "refund window", "predicate": "is", "object": "30 days", "entity_hint": "refund_policy"},
        "claim_b": {"subject": "refund window", "predicate": "is", "object": "15 days", "entity_hint": "refund_policy"},
        "expected_severity": "high",
    },
    {
        "id": "CANARY-002",
        "system_a_name": "CanarySystemA",
        "system_b_name": "CanarySystemB",
        "claim_a": {"subject": "medication X", "predicate": "is contraindicated below eGFR", "object": "45 mL/min", "entity_hint": "clinical"},
        "claim_b": {"subject": "medication X", "predicate": "is contraindicated below eGFR", "object": "30 mL/min", "entity_hint": "clinical"},
        "expected_severity": "critical",
    },
]

@celery_app.task
def run_canary_check():
    """Runs every hour via Beat. Injects canary pairs, waits, verifies detection."""
    from workers.tasks import process_sample_task
    from services.embedder import embed_text  # see section 4

    db: Session = SessionLocal()
    failures = []
    try:
        for canary in CANARY_PAIRS:
            sys_a = _get_or_create_canary_system(db, canary["system_a_name"])
            sys_b = _get_or_create_canary_system(db, canary["system_b_name"])

            text_a = f"{canary['claim_a']['subject']} {canary['claim_a']['predicate']} {canary['claim_a']['object']}"
            text_b = f"{canary['claim_b']['subject']} {canary['claim_b']['predicate']} {canary['claim_b']['object']}"

            process_sample_task.delay(str(sys_a.id), text_a, {"canary_id": canary["id"]})
            process_sample_task.delay(str(sys_b.id), text_b, {"canary_id": canary["id"]})

        # Schedule verification 5 min later
        verify_canary_results.apply_async(args=[[c["id"] for c in CANARY_PAIRS]], countdown=300)
    finally:
        db.close()

@celery_app.task
def verify_canary_results(canary_ids: list[str]):
    """Verifies each canary produced an open contradiction. Alerts on miss."""
    db = SessionLocal()
    try:
        for canary_id in canary_ids:
            expected = next(c for c in CANARY_PAIRS if c["id"] == canary_id)
            found = db.query(Contradiction).join(...).filter(
                # Match by canary metadata or entity_hint scoping
                Contradiction.status == "open",
                Contradiction.detected_at >= datetime.now(timezone.utc) - timedelta(minutes=10)
            ).first()

            if not found:
                logger.critical(f"🚨 CANARY MISS: {canary_id} not detected. Detection pipeline degraded.")
                # Dispatch high-priority Slack alert
                from workers.alert_dispatcher import send_canary_miss_alert
                send_canary_miss_alert(canary_id)
    finally:
        db.close()

def _get_or_create_canary_system(db, name):
    sys = db.query(System).filter_by(name=name).first()
    if not sys:
        sys = System(name=name, provider="canary", description="F8.1 health probe")
        db.add(sys); db.commit(); db.refresh(sys)
    return sys