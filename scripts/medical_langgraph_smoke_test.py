"""
Sprint 9 Task 4 smoke test.

Assumes MedicalAgent container is running the new langgraph_agent module.
Hits its /health and /respond endpoints, verifies canon lookup fires,
LLM returns a well-shaped claim, and Orqestra extracts at least one
claim within ~10s.

Prereqs (all should already be done from Sprint 8 + Task 3):
  - demo-fitness org seeded
  - Canon declarations populated (declare_demo_canon.py)
  - MedicalAgent container running langgraph_agent (see Task 4 notes
    for the docker-compose.yml swap)

Run:
  docker compose exec api python -m scripts.medical_langgraph_smoke_test
"""
import logging
import sys
import time

import requests
from sqlalchemy import text as sql_text

from core.database import SessionLocal
from models.database import Organization, System

logging.basicConfig(level=logging.INFO, format="[med_lg_smoke] %(message)s")
logger = logging.getLogger(__name__)

# Local to the api container; use the compose service name for the agent.
MEDICAL_AGENT_URL = "http://medical_agent:8102"
DEMO_ORG_SLUG = "demo-fitness"
TARGET_AGENT_NAME = "MedicalAgent"


def _lookup_medical_agent_system_id() -> str:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        sys_ = db.query(System).filter_by(org_id=org.id, name=TARGET_AGENT_NAME).first()
        return str(sys_.id)
    finally:
        db.close()


def _count_claims_for_system(system_id: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            sql_text("SELECT COUNT(*) FROM claims WHERE system_id = :sid"),
            {"sid": system_id},
        ).scalar() or 0
    finally:
        db.close()


def _http_with_retry(method, url, retries=15, delay=0.5, **kw):
    last_exc = None
    for attempt in range(retries):
        try:
            return requests.request(method, url, **kw)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            time.sleep(delay * (attempt + 1))
    raise last_exc


def main():
    system_id = _lookup_medical_agent_system_id()
    logger.info(f"MedicalAgent system_id={system_id}")

    logger.info(f"probing {MEDICAL_AGENT_URL}/health …")
    r = _http_with_retry("GET", f"{MEDICAL_AGENT_URL}/health", timeout=10)
    if r.status_code != 200:
        logger.error(f"❌ health check failed: {r.status_code} {r.text[:200]}")
        sys.exit(2)
    health = r.json()
    logger.info(f"health: executor={health.get('executor')} kb_loaded={health.get('kb_loaded')}")
    if health.get("executor") != "langgraph":
        logger.error("❌ MedicalAgent container is NOT running the langgraph executor")
        sys.exit(2)
    logger.info(f"✓ langgraph executor active; valid_entities={health.get('valid_entities')}")

    before = _count_claims_for_system(system_id)
    logger.info(f"claims before /respond: {before}")

    trigger = (
        "User asked whether they can add heavy barbell squats to their "
        "workout routine this week. Assess medically."
    )
    logger.info(f"POST /respond trigger='{trigger[:60]}…'")
    r = _http_with_retry(
        "POST",
        f"{MEDICAL_AGENT_URL}/respond",
        json={"trigger": trigger},
        timeout=60,
    )
    if r.status_code != 200:
        logger.error(f"❌ /respond failed: {r.status_code} {r.text[:400]}")
        sys.exit(2)
    body = r.json()

    claim = body.get("claim") or {}
    gt = body.get("canon_ground_truth") or {}
    node_events = body.get("node_events") or []

    logger.info(f"agent returned claim.entity={claim.get('entity')!r}")
    logger.info(f"claim.claim_text={claim.get('claim_text')!r}")
    logger.info(f"node_events (end only): {node_events}")

    declared_names = [n for n, r_ in gt.items() if r_.get("status") == "declared"]
    logger.info(f"canon declared for this agent: {declared_names}")

    # Assertions
    if not claim.get("claim_text"):
        logger.error("❌ agent returned no claim_text")
        sys.exit(2)
    if claim.get("entity") not in health.get("valid_entities", []):
        logger.error(f"❌ agent entity {claim.get('entity')!r} not in valid_entities")
        sys.exit(2)
    if len(node_events) < 2:
        logger.error(f"❌ expected 2 node end events, got {len(node_events)}")
        sys.exit(2)
    node_names = {e["node"] for e in node_events}
    if node_names != {"canon_lookup", "respond"}:
        logger.error(f"❌ unexpected node set: {node_names}")
        sys.exit(2)

    logger.info("✓ claim well-shaped, both nodes fired, canon lookup succeeded")

    for wait in [1.0, 2.0, 3.0, 4.0]:
        time.sleep(wait)
        after = _count_claims_for_system(system_id)
        if after > before:
            logger.info(f"✅ claim extracted after {wait}s wait (before={before}, after={after})")
            return
        logger.info(f"  no new claim yet after {wait}s (count={after})")

    logger.error(f"❌ no claim extracted after 10s (before={before}, after={after})")
    sys.exit(2)


if __name__ == "__main__":
    main()