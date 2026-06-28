import os, uuid, logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from core.celery_app import celery_app
from core.database import SessionLocal
from models.database import System, Claim, Contradiction, Organization
from observability import get_logger

logger = get_logger(__name__)

CANARY_ORG_SLUG = "canary-probe"
CANARY_ORG_NAME = "Canary Probe"

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


def _get_or_create_canary_org(db: Session) -> Organization:
    org = db.query(Organization).filter_by(slug=CANARY_ORG_SLUG).first()
    if not org:
        org = Organization(
            name=CANARY_ORG_NAME,
            slug=CANARY_ORG_SLUG,
            vertical_preset="general",
            description="F8.1 canary probe tenant — synthetic contradictions for pipeline health checks.",
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        logger.info(f"Created canary org {org.id}")
    return org


def _get_or_create_canary_system(db: Session, name: str, org_id) -> System:
    # System.name is globally unique, so filter by name only; verify org match
    sys = db.query(System).filter_by(name=name).first()
    if sys and sys.org_id != org_id:
        raise RuntimeError(
            f"Canary system name '{name}' already exists under a different org. "
            f"Rename collision — investigate or rename the canary."
        )
    if not sys:
        sys = System(
            name=name,
            org_id=org_id,
            provider="canary",
            description="F8.1 health probe",
        )
        db.add(sys)
        db.commit()
        db.refresh(sys)
    return sys


@celery_app.task
def run_canary_check():
    """Runs hourly via Beat. Injects canary pairs scoped to canary org, verifies later."""
    from workers.tasks import process_sample_task

    db: Session = SessionLocal()
    try:
        org = _get_or_create_canary_org(db)

        for canary in CANARY_PAIRS:
            sys_a = _get_or_create_canary_system(db, canary["system_a_name"], org.id)
            sys_b = _get_or_create_canary_system(db, canary["system_b_name"], org.id)

            text_a = f"{canary['claim_a']['subject']} {canary['claim_a']['predicate']} {canary['claim_a']['object']}"
            text_b = f"{canary['claim_b']['subject']} {canary['claim_b']['predicate']} {canary['claim_b']['object']}"

            process_sample_task.delay(str(sys_a.id), text_a, {"canary_id": canary["id"]})
            process_sample_task.delay(str(sys_b.id), text_b, {"canary_id": canary["id"]})

        verify_canary_results.apply_async(
            args=[[c["id"] for c in CANARY_PAIRS], str(org.id)],
            countdown=300,
        )
    finally:
        db.close()


@celery_app.task
def verify_canary_results(canary_ids: list[str], org_id: str):
    """Verifies each canary produced an open contradiction within the canary org. Alerts on miss."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        for canary_id in canary_ids:
            found = (
                db.query(Contradiction)
                .filter(
                    Contradiction.org_id == org_id,
                    Contradiction.status == "open",
                    Contradiction.detected_at >= cutoff,
                )
                .first()
            )
            if not found:
                logger.critical(f"🚨 CANARY MISS: {canary_id} not detected. Detection pipeline degraded.")
                try:
                    from workers.alert_dispatcher import send_canary_miss_alert
                    send_canary_miss_alert(canary_id)
                except Exception as e:
                    logger.error(f"Failed to dispatch canary miss alert: {e}")
    finally:
        db.close()