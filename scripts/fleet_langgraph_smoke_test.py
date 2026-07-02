"""
Sprint 9 Task 5 smoke test.

Assumes all five demo agents run the langgraph executor. Hits each
agent's /respond with a domain-relevant trigger, verifies each returns
a well-shaped claim with entity in its valid set, and confirms claims
land in the DB.

Pass criteria:
  - All 5 agents report executor=langgraph on /health
  - Each /respond returns HTTP 200 with a claim.entity in that agent's
    valid_entities set
  - Each agent's claim count strictly increases after its call
  - Every agent's response includes canon_ground_truth (dict, possibly
    empty for agents whose entities aren't declared)
"""
import logging
import sys
import time

import requests
from sqlalchemy import text as sql_text

from core.database import SessionLocal
from models.database import Organization, System

logging.basicConfig(level=logging.INFO, format="[fleet_smoke] %(message)s")
logger = logging.getLogger(__name__)

DEMO_ORG_SLUG = "demo-fitness"

# Each entry: (agent name in DB, container hostname, port, trigger phrase)
_RUN_ID = int(time.time())

AGENTS = [
    (   
        "FitnessAgent", "fitness_agent", 8101,
        f"User asked for a suggested workout routine for this week (run {_RUN_ID})."
    ),
    (
        "MedicalAgent", "medical_agent", 8102,
        f"User asked whether they can add heavy barbell squats to their "
        f"workout routine this week (run {_RUN_ID}). Assess medically."
    ),
    (
        "NutritionAgent", "nutrition_agent", 8103,
        f"User asked what daily meal plan best supports current training "
        f"and recovery load (run {_RUN_ID})."
    ),
    (
        "RecoveryAgent", "recovery_agent", 8104,
        f"User asked what recovery protocol is appropriate given current "
        f"training volume and HRV trend (run {_RUN_ID})."
    ),
    (
        "BudgetAgent", "budget_agent", 8105,
        f"User asked what monthly spending on supplements and coaching "
        f"is appropriate for their goals (run {_RUN_ID})."
    ),
]


def _http_with_retry(method, url, retries=15, delay=0.5, **kw):
    last_exc = None
    for attempt in range(retries):
        try:
            return requests.request(method, url, **kw)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            time.sleep(delay * (attempt + 1))
    raise last_exc


def _lookup_system_ids() -> dict[str, str]:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        if not org:
            raise RuntimeError(f"org {DEMO_ORG_SLUG} not found")
        out: dict[str, str] = {}
        for name, _, _, _ in AGENTS:
            s = db.query(System).filter_by(org_id=org.id, name=name).first()
            if not s:
                raise RuntimeError(f"system {name} not found in {DEMO_ORG_SLUG}")
            out[name] = str(s.id)
        return out
    finally:
        db.close()


def _count_claims(system_id: str) -> int:
    db = SessionLocal()
    try:
        # Force a fresh read: rollback ends any implicit transaction the
        # pooled connection may be holding, giving us the current committed
        # state instead of a stale snapshot.
        db.rollback()
        return db.execute(
            sql_text("SELECT COUNT(*) FROM claims WHERE system_id = :s"),
            {"s": system_id},
        ).scalar() or 0
    finally:
        db.close()


def main():
    system_ids = _lookup_system_ids()

    # 1. Health check all 5
    logger.info("=== phase 1: health check all agents ===")
    healths: dict[str, dict] = {}
    for name, host, port, _ in AGENTS:
        r = _http_with_retry("GET", f"http://{host}:{port}/health", timeout=10)
        if r.status_code != 200:
            logger.error(f"❌ {name} health {r.status_code}: {r.text[:200]}")
            sys.exit(2)
        j = r.json()
        if j.get("executor") != "langgraph":
            logger.error(f"❌ {name} executor={j.get('executor')} (want langgraph)")
            sys.exit(2)
        healths[name] = j
        logger.info(
            f"✓ {name:16s} executor=langgraph  entities={len(j.get('valid_entities', []))}"
        )

    # 2. Snapshot claim counts before firing
    logger.info("=== phase 2: snapshot claim counts ===")
    before: dict[str, int] = {}
    for name, _, _, _ in AGENTS:
        before[name] = _count_claims(system_ids[name])
        logger.info(f"  {name:16s} before={before[name]}")

    # 3. Fire each agent, validate the returned claim shape
    logger.info("=== phase 3: fire each agent ===")
    fired: list[str] = []
    for name, host, port, trigger in AGENTS:
        r = _http_with_retry(
            "POST",
            f"http://{host}:{port}/respond",
            json={"trigger": trigger},
            timeout=90,
        )
        if r.status_code != 200:
            logger.error(f"❌ {name} /respond {r.status_code}: {r.text[:300]}")
            sys.exit(2)
        body = r.json()

        claim = body.get("claim") or {}
        gt = body.get("canon_ground_truth")
        node_events = body.get("node_events") or []

        if not isinstance(gt, dict):
            logger.error(f"❌ {name} canon_ground_truth is not a dict: {gt!r}")
            sys.exit(2)
        if not claim.get("claim_text"):
            logger.error(f"❌ {name} returned empty claim_text")
            sys.exit(2)
        valid = set(healths[name].get("valid_entities", []))
        if claim.get("entity") not in valid:
            logger.error(
                f"❌ {name} claim.entity={claim.get('entity')!r} "
                f"not in valid set {sorted(valid)}"
            )
            sys.exit(2)
        end_nodes = {e["node"] for e in node_events if e["kind"] == "end"}
        if end_nodes != {"canon_lookup", "respond"}:
            logger.error(f"❌ {name} node end set unexpected: {end_nodes}")
            sys.exit(2)

        declared = [n for n, r_ in gt.items() if r_.get("status") == "declared"]
        logger.info(
            f"✓ {name:16s} entity={claim.get('entity'):24s} "
            f"declared_in_canon={declared}"
        )
        fired.append(name)

    # 4. Poll until each agent's claim count grows
    logger.info("=== phase 4: verify claims land in DB ===")
    pending = set(fired)
    deadline = time.time() + 30.0
    while pending and time.time() < deadline:
        time.sleep(1.5)
        for name in list(pending):
            after = _count_claims(system_ids[name])
            if after > before[name]:
                logger.info(f"  ✓ {name:16s} {before[name]} → {after}")
                pending.discard(name)

    if pending:
        logger.error(
            f"❌ these agents' claims never landed within 30s: {sorted(pending)}"
        )
        for name in sorted(pending):
            after = _count_claims(system_ids[name])
            logger.error(f"    {name}: before={before[name]} still={after}")
        sys.exit(2)

    logger.info("✅ all 5 agents on langgraph, claims flowing end-to-end")


if __name__ == "__main__":
    main()