"""
Reusable LangGraph nodes for authored agents.

Sprint 9 Task 3: canon_lookup_node — a node factory that hits
/canon/resolve for each entity the agent's KB declares interest in and
populates state['canon_ground_truth'].

Design:
  - Node factory: bind (entity_list, api_base, api_token) at graph-build
    time; runtime node just executes the lookup.
  - Never raises — canon lookup errors land as resolution_status='error'
    per entity, agent still responds without ground truth for that entity.
  - Prompt injection is a separate helper (format_canon_block) so nodes
    that don't do LLM calls (e.g. a routing node) can still consume canon.

State contract:
  Input state may contain anything.
  After canon_lookup runs, state['canon_ground_truth'] is a dict:
      {
        "<entity>": {
          "value": <str | None>,
          "claim_text": <str | None>,
          "status": "declared" | "no_declaration" | "error",
        },
        ...
      }
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from services.canon_client import resolve_many
from observability import get_logger

logger = get_logger(__name__)


CANON_STATE_KEY = "canon_ground_truth"


def canon_lookup_node_factory(
    *,
    entities: list[str],
    api_base: str,
    api_token: str,
    timeout: float = 5.0,
    canon_enabled: bool = True,
) -> Callable[[dict], Awaitable[dict]]:
    """
    Returns an async LangGraph node function that resolves the given
    entities and populates state[CANON_STATE_KEY].

    Bind once at graph-build time. The returned callable is what you pass
    to StateGraph.add_node().

    canon_enabled:
        When True (default), performs the /canon/resolve calls as normal.
        When False, returns an empty ground_truth dict without calling
        Canon. Every entity appears as status='disabled' so downstream
        code (format_canon_block, observability) can distinguish "no
        lookup performed" from "lookup returned no_declaration". This is
        Sprint 10's measurement toggle for Canon-on vs Canon-off runs.
    """

    async def canon_lookup(state: dict) -> dict:
        if not canon_enabled:
            ground_truth = {
                name: {"value": None, "claim_text": None, "status": "disabled"}
                for name in entities
            }
            logger.info(
                "canon_lookup_node.completed",
                entities_requested=len(entities),
                canon_enabled=False,
                declared=0,
                no_declaration=0,
                errors=0,
                disabled=len(entities),
            )
            return {CANON_STATE_KEY: ground_truth}

        resolved = await resolve_many(
            entities=entities,
            api_base=api_base,
            api_token=api_token,
            timeout=timeout,
        )

        ground_truth: dict[str, dict] = {}
        declared_count = 0
        error_count = 0
        for name in entities:
            r = resolved.get(name, {})
            status = r.get("resolution_status", "error")
            ground_truth[name] = {
                "value": r.get("canonical_value"),
                "claim_text": r.get("canonical_claim_text"),
                "status": status,
            }
            if status == "declared":
                declared_count += 1
            elif status == "error":
                error_count += 1

        logger.info(
            "canon_lookup_node.completed",
            entities_requested=len(entities),
            canon_enabled=True,
            declared=declared_count,
            no_declaration=len(entities) - declared_count - error_count,
            errors=error_count,
        )

        return {CANON_STATE_KEY: ground_truth}

    return canon_lookup


def format_canon_block(ground_truth: dict[str, dict]) -> str:
    """
    Format the canon_ground_truth dict into a block suitable for injection
    into an LLM system prompt. Only DECLARED values are included — no
    'no_declaration' or 'error' rows, so the model isn't confused by
    blank truth signals.

    Returns "" (empty string) if no entities were declared. Caller should
    check `if block:` before injecting, so the prompt isn't bloated with
    an empty <canon_ground_truth> section.
    """
    declared_rows = [
        (name, row) for name, row in ground_truth.items()
        if row.get("status") == "declared" and row.get("value")
    ]
    if not declared_rows:
        return ""

    lines = ["<canon_ground_truth>"]
    lines.append("The following facts have been declared canonical for this organization.")
    lines.append("You MUST treat them as authoritative and MUST NOT contradict them.")
    lines.append("")
    for name, row in declared_rows:
        lines.append(f"- {name}: {row['value']}")
        claim_text = row.get("claim_text")
        if claim_text and claim_text != row["value"]:
            lines.append(f"    ({claim_text})")
    lines.append("</canon_ground_truth>")
    return "\n".join(lines)