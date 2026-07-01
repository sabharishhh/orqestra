"""Read JSON log lines, print p50/p95/p99 per timed event.

Reads from stdin or a file path:
    docker compose logs api worker_default --no-color | python scripts/log_summary.py
    python scripts/log_summary.py path/to/logs.jsonl

Grouped by event type (request.completed, db.query, detection.level.completed,
llm.call, embedding.call, task.completed). Within each event, optionally
sub-grouped by a discriminating field (path, query_name, funnel_level, purpose,
task_name).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from statistics import median

# Events to summarize and their discriminator field for sub-grouping
EVENT_GROUPING = {
    "request.completed": "path",
    "db.query": "query_name",
    "detection.level.completed": "funnel_level",
    "llm.call": "purpose",
    "embedding.call": None,  # no sub-grouping
    "task.completed": "task_name",
}

# Strip docker-compose log prefixes like "api-1 | " or "worker_default-1  |"
DC_PREFIX = re.compile(r"^[a-zA-Z0-9_-]+-\d+\s*\|\s*")


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile. p in [0, 100]."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def parse_line(line: str) -> dict | None:
    line = DC_PREFIX.sub("", line.strip())
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="Path to log file (default: stdin)")
    ap.add_argument("--org", help="Filter to a single org_slug")
    args = ap.parse_args()

    src = open(args.path) if args.path else sys.stdin

    # {(event, sub_key): [durations_ms]}
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    # Also track total tokens + cost where applicable
    tokens_by_purpose: dict[str, int] = defaultdict(int)
    cost_total: float = 0.0

    for raw in src:
        obj = parse_line(raw)
        if obj is None:
            continue
        if args.org and obj.get("org_slug") != args.org:
            continue
        event = obj.get("event")
        if event not in EVENT_GROUPING:
            continue
        duration = obj.get("duration_ms")
        if duration is None:
            continue
        sub_field = EVENT_GROUPING[event]
        sub_val = "-" if sub_field is None else str(obj.get(sub_field, "-"))
        buckets[(event, sub_val)].append(float(duration))

        if event == "llm.call":
            tokens_by_purpose[str(obj.get("purpose", "unknown"))] += int(obj.get("total_tokens") or 0)
            cost_total += float(obj.get("est_cost_usd") or 0.0)
        elif event == "embedding.call":
            tokens_by_purpose["embedding"] += int(obj.get("input_tokens") or 0)
            cost_total += float(obj.get("est_cost_usd") or 0.0)

    if not buckets:
        print("No matching log lines parsed.", file=sys.stderr)
        return 1

    print(f"\n{'event':<32} {'sub_key':<48} {'count':>7} {'p50':>9} {'p95':>9} {'p99':>9}  (durations in ms)")
    print("-" * 120)

    by_event: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    for (event, sub_val), values in buckets.items():
        by_event[event].append((sub_val, values))

    for event in sorted(by_event.keys()):
        rows = sorted(by_event[event], key=lambda r: -len(r[1]))
        for sub_val, values in rows:
            sub_display = (sub_val[:46] + "..") if len(sub_val) > 48 else sub_val
            print(
                f"{event:<32} {sub_display:<48} {len(values):>7} "
                f"{percentile(values, 50):>9.2f} {percentile(values, 95):>9.2f} "
                f"{percentile(values, 99):>9.2f}"
            )
        print()

    if tokens_by_purpose:
        print("Token usage by purpose:")
        for purpose, tok in sorted(tokens_by_purpose.items(), key=lambda r: -r[1]):
            print(f"  {purpose:<24} {tok:>10} tokens")
        print(f"  {'TOTAL est cost':<24} ${cost_total:>10.6f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())