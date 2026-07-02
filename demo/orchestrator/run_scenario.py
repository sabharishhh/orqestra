"""
Sprint 9 Task 6 — Fleet orchestrator.

Fires all 5 agents in parallel against a scenario file, waits for the
pipeline to settle, then prints a summary showing what each agent
asserted and what contradictions emerged.

This is the runnable demo artifact — the thing that says, in one command:
"here is the estate running." It is deliberately thin. It does not route
messages between agents, it does not coordinate their semantics, it does
not adjudicate. Agents post claims independently; contradictions emerge
in Orqestra's detection funnel; the orchestrator just drives the
scenario and reports the state.

Design notes:
  - Scenario files are the source of truth for demo inputs. The
    orchestrator has zero hardcoded triggers.
  - Fleet infra (host + port per agent) lives in FLEET_CONFIG below,
    NOT in the scenario file — scenarios are about story, infra is
    about deployment.
  - Sprint 10 will use this same runner to drive Canon-on vs Canon-off
    A/B measurement runs.

Usage:
  docker compose exec api python -m demo.orchestrator.run_scenario
  docker compose exec api python -m demo.orchestrator.run_scenario \\
      --scenario demo/scenarios/acl_recovery_conflict.yaml
  docker compose exec api python -m demo.orchestrator.run_scenario \\
      --scenario ... --json   # emit machine-readable summary
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import text as sql_text

from core.database import SessionLocal
from models.database import Organization, System

logging.basicConfig(level=logging.INFO, format="[orchestrator] %(message)s")
logger = logging.getLogger(__name__)


# =====================================================
# Infra config — where each agent lives on the compose network.
# NOT scenario-driven; this is deployment concern.
# =====================================================
FLEET_CONFIG: dict[str, tuple[str, int]] = {
    "FitnessAgent":   ("fitness_agent",   8101),
    "MedicalAgent":   ("medical_agent",   8102),
    "NutritionAgent": ("nutrition_agent", 8103),
    "RecoveryAgent":  ("recovery_agent",  8104),
    "BudgetAgent":    ("budget_agent",    8105),
}

DEFAULT_SCENARIO_PATH = "demo/scenarios/acl_recovery_conflict.yaml"


# =====================================================
# Scenario loading
# =====================================================
@dataclass
class ScenarioAgentTrigger:
    name: str
    trigger: str


@dataclass
class Scenario:
    scenario_id: str
    description: str
    org_slug: str
    post_fire_wait_seconds: float
    agents: list[ScenarioAgentTrigger]


def load_scenario(path: Path) -> Scenario:
    with open(path) as f:
        raw = yaml.safe_load(f)

    if "agents" not in raw or not isinstance(raw["agents"], list):
        raise ValueError(f"{path}: 'agents' list is required")

    agents: list[ScenarioAgentTrigger] = []
    for entry in raw["agents"]:
        if "name" not in entry or "trigger" not in entry:
            raise ValueError(
                f"{path}: each agent entry must have 'name' and 'trigger'"
            )
        if entry["name"] not in FLEET_CONFIG:
            raise ValueError(
                f"{path}: unknown agent '{entry['name']}'. "
                f"Known: {sorted(FLEET_CONFIG)}"
            )
        agents.append(ScenarioAgentTrigger(
            name=entry["name"],
            trigger=entry["trigger"].strip(),
        ))

    return Scenario(
        scenario_id=raw.get("scenario_id", path.stem),
        description=raw.get("description", "").strip(),
        org_slug=raw.get("org_slug", "demo-fitness"),
        post_fire_wait_seconds=float(raw.get("post_fire_wait_seconds", 20)),
        agents=agents,
    )


# =====================================================
# Snapshot helpers — count claims/contradictions per org
# =====================================================
def _org_id_for(slug: str) -> str:
    db = SessionLocal()
    try:
        db.rollback()  # force fresh snapshot on pooled connection
        org = db.query(Organization).filter_by(slug=slug).first()
        if not org:
            raise RuntimeError(f"Org '{slug}' not found. Run seed_org first.")
        return str(org.id)
    finally:
        db.close()


def _agent_system_id_map(org_slug: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        db.rollback()
        org = db.query(Organization).filter_by(slug=org_slug).first()
        out = {}
        for name in FLEET_CONFIG:
            s = db.query(System).filter_by(org_id=org.id, name=name).first()
            if s:
                out[name] = str(s.id)
        return out
    finally:
        db.close()


def _snapshot_state(org_id: str, system_ids: dict[str, str]) -> dict:
    db = SessionLocal()
    try:
        db.rollback()

        claim_counts: dict[str, int] = {}
        for name, sid in system_ids.items():
            claim_counts[name] = db.execute(
                sql_text("SELECT COUNT(*) FROM claims WHERE system_id = :s"),
                {"s": sid},
            ).scalar() or 0

        total_claims = db.execute(
            sql_text("SELECT COUNT(*) FROM claims WHERE org_id = :o"),
            {"o": org_id},
        ).scalar() or 0

        total_contradictions = db.execute(
            sql_text("SELECT COUNT(*) FROM contradictions WHERE org_id = :o"),
            {"o": org_id},
        ).scalar() or 0

        return {
            "claim_counts": claim_counts,
            "total_claims": total_claims,
            "total_contradictions": total_contradictions,
        }
    finally:
        db.close()


def _recent_contradictions(org_id: str, limit: int = 10) -> list[dict]:
    """Fetch the most recent contradictions in the org."""
    db = SessionLocal()
    try:
        db.rollback()
        rows = db.execute(sql_text("""
            SELECT
                c.id,
                c.severity,
                c.status,
                c.cosine_similarity,
                c.nli_score,
                c.detected_at,
                e.canonical_name AS entity_name,
                sa.name AS system_a_name,
                sb.name AS system_b_name,
                ca.subject AS claim_a_subject,
                ca.predicate AS claim_a_predicate,
                ca.object AS claim_a_object,
                cb.subject AS claim_b_subject,
                cb.predicate AS claim_b_predicate,
                cb.object AS claim_b_object
            FROM contradictions c
            JOIN claims ca ON ca.id = c.claim_a_id
            JOIN claims cb ON cb.id = c.claim_b_id
            JOIN systems sa ON sa.id = ca.system_id
            JOIN systems sb ON sb.id = cb.system_id
            LEFT JOIN canonical_entities e ON e.id = c.entity_id
            WHERE c.org_id = :o
            ORDER BY c.detected_at DESC
            LIMIT :lim
        """), {"o": org_id, "lim": limit}).all()

        return [
            {
                "id": str(r.id),
                "severity": r.severity,
                "status": r.status,
                "cosine": float(r.cosine_similarity) if r.cosine_similarity is not None else None,
                "nli": float(r.nli_score) if r.nli_score is not None else None,
                "entity": r.entity_name,
                "detected_at": r.detected_at.isoformat() if r.detected_at else None,
                "systems": [r.system_a_name, r.system_b_name],
                "claim_a": f"{r.claim_a_subject} {r.claim_a_predicate} {r.claim_a_object}",
                "claim_b": f"{r.claim_b_subject} {r.claim_b_predicate} {r.claim_b_object}",
            }
            for r in rows
        ]
    finally:
        db.close()


# =====================================================
# Fire the fleet — parallel via httpx.AsyncClient
# =====================================================
async def _fire_one(
    client: httpx.AsyncClient,
    name: str,
    host: str,
    port: int,
    trigger: str,
) -> dict:
    url = f"http://{host}:{port}/respond"
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json={"trigger": trigger}, timeout=90.0)
    except httpx.HTTPError as e:
        return {"agent": name, "ok": False, "error": f"transport: {e!s}"}
    dur_ms = (time.perf_counter() - t0) * 1000

    if r.status_code != 200:
        return {
            "agent": name, "ok": False,
            "error": f"http {r.status_code}: {r.text[:200]}",
            "duration_ms": round(dur_ms, 1),
        }
    body = r.json()
    return {
        "agent": name,
        "ok": True,
        "duration_ms": round(dur_ms, 1),
        "claim_text": (body.get("claim") or {}).get("claim_text"),
        "entity": (body.get("claim") or {}).get("entity"),
        "canon_declared": [
            n for n, row in (body.get("canon_ground_truth") or {}).items()
            if row.get("status") == "declared"
        ],
    }


async def _fire_fleet(scenario: Scenario) -> list[dict]:
    async with httpx.AsyncClient() as client:
        tasks = []
        for a in scenario.agents:
            host, port = FLEET_CONFIG[a.name]
            tasks.append(_fire_one(client, a.name, host, port, a.trigger))
        return await asyncio.gather(*tasks)


# =====================================================
# Reporting
# =====================================================
def _print_report(
    scenario: Scenario,
    fire_results: list[dict],
    before: dict,
    after: dict,
    contradictions: list[dict],
):
    print()
    print("=" * 72)
    print(f"Scenario: {scenario.scenario_id}")
    print("=" * 72)
    if scenario.description:
        for line in scenario.description.splitlines():
            print(f"  {line}")
    print()

    print("─── Fleet fire ─────────────────────────────────────────────────────────")
    for r in fire_results:
        if r["ok"]:
            print(f"  ✓ {r['agent']:16s} entity={r['entity']:24s} "
                  f"({r['duration_ms']:.0f}ms)")
            print(f"      claim: {r['claim_text']}")
            if r["canon_declared"]:
                print(f"      canon: {r['canon_declared']}")
        else:
            print(f"  ✗ {r['agent']:16s} FAIL: {r['error']}")
    print()

    print("─── Claim deltas ───────────────────────────────────────────────────────")
    for name in FLEET_CONFIG:
        b = before["claim_counts"].get(name, 0)
        a = after["claim_counts"].get(name, 0)
        delta = a - b
        marker = "+" if delta > 0 else " "
        print(f"  {name:16s} {b:4d} → {a:4d}  ({marker}{delta})")
    print(f"  {'TOTAL':16s} {before['total_claims']:4d} → {after['total_claims']:4d}  "
          f"(+{after['total_claims'] - before['total_claims']})")
    print()

    print("─── Contradictions in org ──────────────────────────────────────────────")
    delta = after["total_contradictions"] - before["total_contradictions"]
    print(f"  before: {before['total_contradictions']}   "
          f"after: {after['total_contradictions']}   (Δ +{delta})")
    if contradictions:
        print()
        print("  most recent (up to 10):")
        for c in contradictions:
            sev = c["severity"] or "?"
            nli = f"{c['nli']:.2f}" if c['nli'] is not None else "?"
            cos = f"{c['cosine']:.2f}" if c['cosine'] is not None else "?"
            entity = c["entity"] or "?"
            status = c["status"] or "?"
            print(f"    • [{sev}/{status}] entity={entity} "
                  f"nli={nli} cos={cos} systems={c['systems']}")
            print(f"      A: {c['claim_a']}")
            print(f"      B: {c['claim_b']}")
    print()
    print("=" * 72)


# =====================================================
# Entrypoint
# =====================================================
async def _amain(args):
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        logger.error(f"scenario file not found: {scenario_path}")
        sys.exit(1)

    scenario = load_scenario(scenario_path)
    logger.info(f"scenario loaded: {scenario.scenario_id} "
                f"({len(scenario.agents)} agents, org={scenario.org_slug})")

    org_id = _org_id_for(scenario.org_slug)
    system_ids = _agent_system_id_map(scenario.org_slug)

    logger.info("snapshot before fire …")
    before = _snapshot_state(org_id, system_ids)

    logger.info(f"firing {len(scenario.agents)} agents in parallel …")
    fire_results = await _fire_fleet(scenario)

    logger.info(f"waiting {scenario.post_fire_wait_seconds}s for pipeline to settle …")
    await asyncio.sleep(scenario.post_fire_wait_seconds)

    logger.info("snapshot after fire …")
    after = _snapshot_state(org_id, system_ids)
    contradictions = _recent_contradictions(org_id, limit=10)

    if args.json:
        payload = {
            "scenario_id": scenario.scenario_id,
            "org_slug": scenario.org_slug,
            "fire_results": fire_results,
            "before": before,
            "after": after,
            "recent_contradictions": contradictions,
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_report(scenario, fire_results, before, after, contradictions)

    # Exit non-zero if any agent failed to fire — the pipeline itself is
    # allowed to produce zero new claims (dedup) or zero new contradictions
    # (all agreement); those are legitimate demo outcomes, not failures.
    failed = [r for r in fire_results if not r["ok"]]
    if failed:
        logger.error(f"{len(failed)} agent(s) failed to fire")
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(
        description="Fire the Orqestra demo fleet against a scenario."
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO_PATH,
        help=f"Path to scenario YAML (default: {DEFAULT_SCENARIO_PATH})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human report",
    )
    args = parser.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()