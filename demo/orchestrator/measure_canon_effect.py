"""
Sprint 10 Task 2 — Canon-on vs Canon-off measurement runner.

Runs a scenario N times against the current fleet configuration and
records per-run deltas: new claims, new contradictions (by severity),
which agents disagreed. Emits a per-phase JSON file. A separate --phase
report step reads both JSONs and prints the Canon-on vs Canon-off
comparison.

Operator's job (fleet-wide toggle, matches Sprint 10 scope):
  1. Bring fleet up with Canon ON, run this in canon_on phase.
  2. Bring fleet up with Canon OFF, run this in canon_off phase.
  3. Run this in report phase to compare.

Runner's job:
  - Assert the fleet's actual canon_enabled state matches the phase
    (--phase canon_on requires all 5 agents at canon_enabled=True,
    canon_off requires all at False). Refuses to run if mismatched —
    catches operator mistakes at the start of a 10-minute run, not
    at the end.
  - Vary the trigger per run so we don't hit F1.2 dedup.
  - Snapshot: claims per agent, total claims, total contradictions,
    contradictions by severity.
  - Per-run delta = after - before.
  - Aggregate: mean/median/stdev across N runs per condition.

Usage:
  # After bringing fleet up with Canon ON:
  docker compose exec api python -m demo.orchestrator.measure_canon_effect \\
      --phase canon_on --runs 5

  # Then flip and re-run:
  #   ORQESTRA_CANON_ENABLED=false docker compose up -d --force-recreate \\
  #       fitness_agent medical_agent nutrition_agent recovery_agent budget_agent
  docker compose exec api python -m demo.orchestrator.measure_canon_effect \\
      --phase canon_off --runs 5

  # Then compare:
  docker compose exec api python -m demo.orchestrator.measure_canon_effect \\
      --phase report
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx
import requests
from sqlalchemy import text as sql_text

from core.database import SessionLocal
from models.database import Organization, System
from demo.orchestrator.run_scenario import (
    FLEET_CONFIG,
    _agent_system_id_map,
    _org_id_for,
    load_scenario,
)

logging.basicConfig(level=logging.INFO, format="[measure] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = "demo/scenarios/acl_recovery_conflict.yaml"
RESULTS_DIR = Path("/mnt/user-data/outputs/sprint10_measurements")

# Per-phase output filenames — deterministic so --phase report can find them.
PHASE_FILES = {
    "canon_on":  "measurement_canon_on.json",
    "canon_off": "measurement_canon_off.json",
}


# =====================================================
# Fleet state assertion
# =====================================================
def _fleet_canon_state() -> dict[str, bool]:
    """Query each agent's /health and return canon_enabled per agent."""
    out: dict[str, bool] = {}
    for name, (host, port) in FLEET_CONFIG.items():
        try:
            r = requests.get(f"http://{host}:{port}/health", timeout=10)
            r.raise_for_status()
            out[name] = bool(r.json().get("canon_enabled"))
        except Exception as e:
            raise RuntimeError(f"can't reach {name} at {host}:{port}: {e}")
    return out


def _assert_fleet_matches_phase(phase: str) -> None:
    want = (phase == "canon_on")
    state = _fleet_canon_state()
    mismatched = [n for n, s in state.items() if s != want]
    if mismatched:
        raise RuntimeError(
            f"phase={phase} requires all agents canon_enabled={want}, "
            f"but these do not match: {mismatched}. "
            f"Full state: {state}"
        )
    logger.info(f"fleet state matches phase={phase} (all 5 agents canon_enabled={want})")


# =====================================================
# Snapshot state
# =====================================================
def _snapshot(org_id: str, system_ids: dict[str, str]) -> dict:
    """
    Snapshot the org's SCCG + contradictions state. Called before and
    after each run; delta = after - before for that run.
    """
    db = SessionLocal()
    try:
        db.rollback()  # force fresh snapshot on pooled conn

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

        by_severity_rows = db.execute(sql_text("""
            SELECT severity, COUNT(*) AS n
            FROM contradictions WHERE org_id = :o
            GROUP BY severity
        """), {"o": org_id}).all()
        contradictions_by_severity = {
            r.severity or "unknown": r.n for r in by_severity_rows
        }

        return {
            "claim_counts": claim_counts,
            "total_claims": total_claims,
            "total_contradictions": total_contradictions,
            "contradictions_by_severity": contradictions_by_severity,
        }
    finally:
        db.close()


def _delta(before: dict, after: dict) -> dict:
    """Compute per-run deltas from snapshots."""
    dclaims = {
        name: after["claim_counts"].get(name, 0) - before["claim_counts"].get(name, 0)
        for name in FLEET_CONFIG
    }
    dsev = {}
    all_sev = set(before["contradictions_by_severity"]) | set(after["contradictions_by_severity"])
    for s in all_sev:
        dsev[s] = (
            after["contradictions_by_severity"].get(s, 0)
            - before["contradictions_by_severity"].get(s, 0)
        )
    return {
        "new_claims_per_agent": dclaims,
        "new_claims_total": after["total_claims"] - before["total_claims"],
        "new_contradictions_total":
            after["total_contradictions"] - before["total_contradictions"],
        "new_contradictions_by_severity": dsev,
    }


# =====================================================
# Fire the fleet — same as run_scenario, but with per-run trigger variation
# =====================================================
async def _fire_one(client, name, host, port, trigger) -> dict:
    url = f"http://{host}:{port}/respond"
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json={"trigger": trigger}, timeout=90.0)
    except Exception as e:
        return {"agent": name, "ok": False, "error": f"transport: {e!s}"}
    dur_ms = (time.perf_counter() - t0) * 1000

    if r.status_code != 200:
        return {"agent": name, "ok": False,
                "error": f"http {r.status_code}: {r.text[:200]}",
                "duration_ms": round(dur_ms, 1)}
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


async def _fire_fleet(scenario, run_id: int) -> list[dict]:
    """
    Fires all scenario agents in parallel. Appends a per-run signature to
    each trigger so different runs don't collide on F1.2 dedup.
    """
    async with httpx.AsyncClient() as client:
        tasks = []
        for a in scenario.agents:
            host, port = FLEET_CONFIG[a.name]
            trigger_variant = (
                f"{a.trigger}\n\n[run signature: run_{run_id} at {int(time.time())}]"
            )
            tasks.append(_fire_one(client, a.name, host, port, trigger_variant))
        return await asyncio.gather(*tasks)


# =====================================================
# One phase = N runs
# =====================================================
async def _run_phase(phase: str, runs: int, scenario_path: Path):
    _assert_fleet_matches_phase(phase)

    scenario = load_scenario(scenario_path)
    logger.info(f"scenario: {scenario.scenario_id}  "
                f"org: {scenario.org_slug}  "
                f"post_fire_wait: {scenario.post_fire_wait_seconds}s")

    org_id = _org_id_for(scenario.org_slug)
    system_ids = _agent_system_id_map(scenario.org_slug)

    per_run: list[dict] = []
    phase_start = time.time()

    for i in range(1, runs + 1):
        logger.info(f"--- {phase} run {i}/{runs} ---")

        before = _snapshot(org_id, system_ids)
        fire_start = time.time()
        fire_results = await _fire_fleet(scenario, run_id=i)
        fire_end = time.time()

        # Sanity: bail if any agent failed to respond. Better to catch
        # halfway through 5 runs than at report time.
        failed = [r for r in fire_results if not r["ok"]]
        if failed:
            logger.error(f"aborting phase: {len(failed)} agent(s) failed to fire: "
                         f"{[r['agent'] for r in failed]}")
            for r in failed:
                logger.error(f"  {r['agent']}: {r.get('error')}")
            sys.exit(2)

        logger.info(f"  fleet fired in {fire_end - fire_start:.1f}s; "
                    f"waiting {scenario.post_fire_wait_seconds}s for pipeline")
        await asyncio.sleep(scenario.post_fire_wait_seconds)

        after = _snapshot(org_id, system_ids)
        d = _delta(before, after)

        # Verify at least ONE agent's canon behaviour matches the phase.
        canon_summary = {
            r["agent"]: r["canon_declared"] for r in fire_results if r["ok"]
        }
        if phase == "canon_on":
            any_declared = any(len(v) > 0 for v in canon_summary.values())
            if not any_declared:
                logger.warning(
                    "  canon_on run produced ZERO declared entities across "
                    "the fleet — either declare_demo_canon hasn't run, or "
                    "agent tokens are stale"
                )
        else:
            any_declared = any(len(v) > 0 for v in canon_summary.values())
            if any_declared:
                logger.error(
                    "  canon_off run somehow saw declared entities: "
                    f"{canon_summary}. Fleet may not actually be off."
                )
                sys.exit(2)

        run_record = {
            "run_id": i,
            "before": before,
            "after": after,
            "delta": d,
            "fire_results": fire_results,
            "fire_duration_s": round(fire_end - fire_start, 2),
        }
        per_run.append(run_record)

        logger.info(
            f"  Δ claims={d['new_claims_total']}  "
            f"Δ contradictions={d['new_contradictions_total']}  "
            f"(by severity: {d['new_contradictions_by_severity']})"
        )

    phase_duration = time.time() - phase_start
    aggregate = _aggregate(per_run)

    result = {
        "phase": phase,
        "runs": runs,
        "scenario_id": scenario.scenario_id,
        "org_slug": scenario.org_slug,
        "phase_duration_s": round(phase_duration, 2),
        "fleet_canon_state": _fleet_canon_state(),
        "per_run": per_run,
        "aggregate": aggregate,
        "recorded_at": int(time.time()),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / PHASE_FILES[phase]
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"wrote {out_path}")

    _print_phase_summary(phase, aggregate)


def _aggregate(per_run: list[dict]) -> dict:
    """Compute mean/median/stdev across runs."""
    if not per_run:
        return {}

    claims_deltas = [r["delta"]["new_claims_total"] for r in per_run]
    contra_deltas = [r["delta"]["new_contradictions_total"] for r in per_run]

    def stats(xs):
        if len(xs) == 0:
            return {"mean": 0, "median": 0, "stdev": 0, "min": 0, "max": 0}
        if len(xs) == 1:
            return {"mean": xs[0], "median": xs[0], "stdev": 0.0,
                    "min": xs[0], "max": xs[0]}
        return {
            "mean": round(statistics.mean(xs), 3),
            "median": round(statistics.median(xs), 3),
            "stdev": round(statistics.stdev(xs), 3),
            "min": min(xs),
            "max": max(xs),
        }

    # Contradictions by severity, summed across runs.
    total_new_contra_by_sev: dict[str, int] = {}
    for r in per_run:
        for sev, n in r["delta"]["new_contradictions_by_severity"].items():
            total_new_contra_by_sev[sev] = total_new_contra_by_sev.get(sev, 0) + n

    return {
        "runs_n": len(per_run),
        "claims_delta_per_run": stats(claims_deltas),
        "contradictions_delta_per_run": stats(contra_deltas),
        "total_new_contradictions_by_severity": total_new_contra_by_sev,
        "total_new_claims_all_runs": sum(claims_deltas),
        "total_new_contradictions_all_runs": sum(contra_deltas),
    }


def _print_phase_summary(phase: str, agg: dict):
    print()
    print("=" * 60)
    print(f"Phase: {phase}   Runs: {agg.get('runs_n')}")
    print("=" * 60)
    c = agg.get("claims_delta_per_run", {})
    x = agg.get("contradictions_delta_per_run", {})
    print(f"  Δ claims per run          mean={c.get('mean')}  "
          f"median={c.get('median')}  stdev={c.get('stdev')}  "
          f"range=[{c.get('min')},{c.get('max')}]")
    print(f"  Δ contradictions per run  mean={x.get('mean')}  "
          f"median={x.get('median')}  stdev={x.get('stdev')}  "
          f"range=[{x.get('min')},{x.get('max')}]")
    print(f"  totals: +{agg.get('total_new_claims_all_runs')} claims, "
          f"+{agg.get('total_new_contradictions_all_runs')} contradictions")
    print(f"  new contradictions by severity: "
          f"{agg.get('total_new_contradictions_by_severity')}")
    print("=" * 60)


# =====================================================
# Report phase: compare canon_on vs canon_off
# =====================================================
def _run_report():
    on_path = RESULTS_DIR / PHASE_FILES["canon_on"]
    off_path = RESULTS_DIR / PHASE_FILES["canon_off"]
    missing = [p for p in (on_path, off_path) if not p.exists()]
    if missing:
        logger.error(f"missing phase file(s): {missing}. "
                     "Run --phase canon_on and --phase canon_off first.")
        sys.exit(1)

    with open(on_path) as f:
        on = json.load(f)
    with open(off_path) as f:
        off = json.load(f)

    on_agg = on["aggregate"]
    off_agg = off["aggregate"]

    on_mean = on_agg["contradictions_delta_per_run"]["mean"]
    off_mean = off_agg["contradictions_delta_per_run"]["mean"]
    delta_mean = off_mean - on_mean

    if off_mean == 0:
        reduction_pct: float | None = None
    else:
        reduction_pct = round((delta_mean / off_mean) * 100, 1)

    print()
    print("=" * 68)
    print("Sprint 10 — Canon effect measurement")
    print("=" * 68)
    print(f"Scenario:  {on['scenario_id']}")
    print(f"Runs:      canon_on={on['runs']}  canon_off={off['runs']}")
    print()
    print("New contradictions per run (mean ± stdev):")
    print(f"  Canon OFF:  {off_mean:5.2f}  ± {off_agg['contradictions_delta_per_run']['stdev']:.2f}"
          f"   range=[{off_agg['contradictions_delta_per_run']['min']}, "
          f"{off_agg['contradictions_delta_per_run']['max']}]")
    print(f"  Canon ON:   {on_mean:5.2f}  ± {on_agg['contradictions_delta_per_run']['stdev']:.2f}"
          f"   range=[{on_agg['contradictions_delta_per_run']['min']}, "
          f"{on_agg['contradictions_delta_per_run']['max']}]")
    print()
    print(f"  Δ (off - on): {delta_mean:+.2f} contradictions/run")
    if reduction_pct is None:
        print("  Reduction:    (undefined — Canon OFF produced 0 contradictions)")
    else:
        print(f"  Reduction:    {reduction_pct:+.1f}%")
    print()
    print("Severity mix (totals across all runs):")
    print(f"  Canon OFF:  {off_agg['total_new_contradictions_by_severity']}")
    print(f"  Canon ON:   {on_agg['total_new_contradictions_by_severity']}")
    print()
    print("New claims per run (Canon should not materially change this):")
    print(f"  Canon OFF:  mean={off_agg['claims_delta_per_run']['mean']:.1f}  "
          f"stdev={off_agg['claims_delta_per_run']['stdev']:.2f}")
    print(f"  Canon ON:   mean={on_agg['claims_delta_per_run']['mean']:.1f}  "
          f"stdev={on_agg['claims_delta_per_run']['stdev']:.2f}")
    print()
    print(f"Files:")
    print(f"  {on_path}")
    print(f"  {off_path}")
    print("=" * 68)


# =====================================================
# Entrypoint
# =====================================================
def main():
    parser = argparse.ArgumentParser(
        description="Sprint 10 Canon-effect measurement runner."
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["canon_on", "canon_off", "report"],
        help="Which measurement phase to run.",
    )
    parser.add_argument(
        "--runs", type=int, default=5,
        help="Number of scenario runs per phase (default 5).",
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO_PATH,
        help=f"Path to scenario YAML (default: {DEFAULT_SCENARIO_PATH})",
    )
    args = parser.parse_args()

    if args.phase == "report":
        _run_report()
        return

    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        logger.error(f"scenario file not found: {scenario_path}")
        sys.exit(1)
    if args.runs < 1:
        logger.error("--runs must be >= 1")
        sys.exit(1)

    asyncio.run(_run_phase(args.phase, args.runs, scenario_path))


if __name__ == "__main__":
    main()