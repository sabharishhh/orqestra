"""
LangGraph provenance probe v2 — fixes v1 bugs:
  - full run_ids (no truncation) so parent linkage is visible
  - full metadata dumps (values, not just keys) — includes langgraph_node
  - checkpoint state values printed alongside metadata
  - explicit YES/NO verdict per path, no eyeballing required

Run:
    source /tmp/probe/bin/activate   # or whatever venv you used
    python probe_langgraph_provenance_v2.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


class ClaimState(TypedDict):
    claims: list[dict]


def node_a(state: ClaimState) -> ClaimState:
    claim = {"text": "User 1RM squat is 95kg", "entity": "user_1rm",
             "agent": "FitnessAgent", "node": "node_a"}
    return {"claims": state.get("claims", []) + [claim]}


def node_b(state: ClaimState) -> ClaimState:
    claim = {"text": "Squat 80kg is 84% of 1RM — above return-to-lift gate",
             "entity": "return_to_lift", "agent": "MedicalAgent", "node": "node_b"}
    return {"claims": state.get("claims", []) + [claim]}


def build_graph():
    g = StateGraph(ClaimState)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)
    g.set_entry_point("node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", END)
    return g.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# PATH 1 — callbacks, with full metadata printed
# ---------------------------------------------------------------------------

class ProvenanceCallback(BaseCallbackHandler):
    def __init__(self):
        self.events: list[dict] = []

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None,
                       tags=None, metadata=None, **kwargs):
        self.events.append({
            "kind": "start",
            "serialized_name": (serialized or {}).get("name"),
            "run_id": str(run_id),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tags": tags,
            "metadata": metadata,   # full dump, not just keys
        })

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        self.events.append({
            "kind": "end",
            "run_id": str(run_id),
            "outputs_keys": list(outputs.keys()) if isinstance(outputs, dict) else None,
        })


def verdict_path1(events: list[dict]) -> str:
    """Look for: node_b's start has parent_run_id == node_a's run_id (causal),
    NOT the graph root run_id (hierarchical)."""
    # Identify by metadata.langgraph_node — that's the true node label
    node_a_run = None
    node_b_run = None
    root_run = None
    for e in events:
        if e["kind"] != "start":
            continue
        md = e.get("metadata") or {}
        node_label = md.get("langgraph_node")
        if node_label == "node_a":
            node_a_run = e["run_id"]
        elif node_label == "node_b":
            node_b_run = e["run_id"]
            node_b_parent = e["parent_run_id"]
        elif e["parent_run_id"] is None:
            root_run = e["run_id"]

    if node_a_run is None or node_b_run is None:
        return f"INCONCLUSIVE — could not identify nodes. a={node_a_run} b={node_b_run}"

    if node_b_parent == node_a_run:
        return f"CAUSAL LINKAGE ✓  (node_b.parent_run_id == node_a.run_id)"
    if node_b_parent == root_run:
        return (f"HIERARCHICAL ONLY ✗  (node_b.parent_run_id == graph_root, "
                f"not node_a). Adapter must derive causality from DAG topology, "
                f"not from parent_run_id.")
    return f"UNEXPECTED — node_b.parent_run_id={node_b_parent}, node_a.run_id={node_a_run}, root={root_run}"


# ---------------------------------------------------------------------------
# PATH 2 — astream_events v2, with full run_ids
# ---------------------------------------------------------------------------

async def path2(events_out: list[dict]) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "probe-p2"}}
    async for ev in graph.astream_events({"claims": []}, config=config, version="v2"):
        etype = ev.get("event", "")
        if etype not in ("on_chain_start", "on_chain_end"):
            continue
        events_out.append({
            "event": etype,
            "name": ev.get("name"),
            "run_id": str(ev.get("run_id")),
            "parent_ids": [str(p) for p in ev.get("parent_ids", [])],
            "tags": ev.get("tags"),
            "metadata": ev.get("metadata"),
        })


def verdict_path2(events: list[dict]) -> str:
    node_a_run = None
    node_b_parents = None
    root_run = None
    for e in events:
        if e["event"] != "on_chain_start":
            continue
        if e["name"] == "node_a":
            node_a_run = e["run_id"]
        elif e["name"] == "node_b":
            node_b_parents = e["parent_ids"]
        elif e["name"] == "LangGraph":
            root_run = e["run_id"]

    if node_a_run is None or node_b_parents is None:
        return f"INCONCLUSIVE — a={node_a_run} b_parents={node_b_parents}"

    if node_a_run in node_b_parents:
        return f"CAUSAL LINKAGE ✓  (node_a's run_id appears in node_b's parent_ids)"
    if root_run and root_run in node_b_parents:
        return (f"HIERARCHICAL ONLY ✗  (node_b.parent_ids contains graph_root, "
                f"not node_a's run_id). Same limitation as Path 1.")
    return f"UNEXPECTED — node_b_parents={node_b_parents}, node_a_run={node_a_run}"


# ---------------------------------------------------------------------------
# PATH 3 — checkpoint history, with .values and full .metadata
# ---------------------------------------------------------------------------

async def path3() -> str:
    graph = build_graph()
    config = {"configurable": {"thread_id": "probe-p3"}}
    await graph.ainvoke({"claims": []}, config=config)

    snapshots = []
    async for cp in graph.aget_state_history(config):
        snapshots.append(cp)

    for cp in snapshots:
        step = (cp.metadata or {}).get("step")
        writes = (cp.metadata or {}).get("writes", {})
        source = (cp.metadata or {}).get("source")
        nxt = list(cp.next) if cp.next else []
        claim_count = len((cp.values or {}).get("claims", []))
        print(f"  step={step:>3}  source={source!r:12}  "
              f"writes_keys={list(writes.keys()) if isinstance(writes, dict) else writes}  "
              f"claim_count={claim_count}  next={nxt}")

    # Verdict: can we identify which node wrote what from writes keys?
    node_names_seen = set()
    for cp in snapshots:
        w = (cp.metadata or {}).get("writes", {})
        if isinstance(w, dict):
            node_names_seen.update(w.keys())

    if {"node_a", "node_b"}.issubset(node_names_seen):
        return "NODE-KEYED WRITES ✓  (metadata['writes'] keyed by node name — usable)"
    elif node_names_seen:
        return f"PARTIAL — writes contained: {node_names_seen}"
    else:
        return ("NO NODE-KEYED WRITES ✗  (metadata['writes'] empty across all "
                "snapshots). Provenance via checkpoints would require diffing "
                "cp.values between snapshots — that is reconstruction.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 72)
    print("PATH 1 — LangChain callbacks (full metadata)")
    print("=" * 72)
    graph = build_graph()
    cb = ProvenanceCallback()
    config = {"configurable": {"thread_id": "probe-p1"}, "callbacks": [cb]}
    await graph.ainvoke({"claims": []}, config=config)
    for e in cb.events:
        print(json.dumps(e, indent=2, default=str))
    print()
    print(">>> VERDICT PATH 1:", verdict_path1(cb.events))
    print()

    print("=" * 72)
    print("PATH 2 — astream_events(v2), full run_ids")
    print("=" * 72)
    p2_events: list[dict] = []
    await path2(p2_events)
    for e in p2_events:
        print(f"{e['event']:20s} name={e['name']:12s} run_id={e['run_id']}")
        print(f"{'':20s} parent_ids={e['parent_ids']}")
    print()
    print(">>> VERDICT PATH 2:", verdict_path2(p2_events))
    print()

    print("=" * 72)
    print("PATH 3 — checkpoint history (values + writes)")
    print("=" * 72)
    v3 = await path3()
    print()
    print(">>> VERDICT PATH 3:", v3)
    print()

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print("If PATH 1 or PATH 2 shows CAUSAL LINKAGE → clean pass, adapter is thin.")
    print("If both show HIERARCHICAL ONLY but node names are extractable →")
    print("   partial pass: adapter maintains DAG topology map + reads event")
    print("   stream for node-name-of-current-step. ~2-3 extra days on Sprint 9.")
    print("If PATH 3 shows NODE-KEYED WRITES that's a bonus recovery path.")


if __name__ == "__main__":
    asyncio.run(main())