"""
LangGraph-based demo agent service.

Sprint 9 Task 4: same interface as demo/agents/agent_service.py
(POST /respond, GET /health) but the response path is now a compiled
LangGraph:

    canon_lookup  →  respond

  - canon_lookup queries /canon/resolve for the intersection of the
    agent's valid_entities and whatever the org has declared.
  - respond calls gpt-5.4-mini with the KB's system prompt PLUS an
    injected <canon_ground_truth> block from the lookup, then formats
    the response as the same pre-tagged text shape that the extraction
    worker has always consumed.

The claim contract from agent_service.py — assertions-not-recommendations,
entity-from-fixed-list, JSON output — is preserved verbatim. Only the
executor changed, not the prompt.

The adapter (services/langgraph_adapter.py) observes the run and posts
the sample. The agent no longer POSTs to /samples directly.

Env vars (same as agent_service.py):
    AGENT_NAME, KB_PATH, USER_PROFILE, ORQESTRA_API, ORQESTRA_KEY,
    ORQESTRA_SYSTEM, OPENAI_API_KEY, PORT
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, TypedDict
from uuid import UUID

import yaml
from fastapi import FastAPI, HTTPException
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from demo.agents.graph_nodes import (
    CANON_STATE_KEY,
    canon_lookup_node_factory,
    format_canon_block,
)
from services.langgraph_adapter import (
    LangGraphAdapter,
    SAMPLE_METADATA_KEY,
    SAMPLE_TEXT_KEY,
)

# ------------------------- Env / KB load -------------------------
AGENT_NAME = os.environ["AGENT_NAME"]
KB_PATH = os.environ["KB_PATH"]
USER_PROFILE_PATH = os.environ["USER_PROFILE"]
ORQESTRA_API = os.environ["ORQESTRA_API"]
ORQESTRA_KEY = os.environ["ORQESTRA_KEY"]
ORQESTRA_SYSTEM = os.environ["ORQESTRA_SYSTEM"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
PORT = int(os.environ.get("PORT", "8100"))

with open(KB_PATH) as f:
    KB = yaml.safe_load(f)
with open(USER_PROFILE_PATH) as f:
    FULL_PROFILE = yaml.safe_load(f)


def _scoped_profile() -> dict:
    """Return ONLY the profile slices this agent is allowed to see."""
    access = KB.get("data_access", {}).get("can_read", [])
    allowed: dict[str, Any] = {"subject_id": FULL_PROFILE["subject_id"]}
    for key in access:
        if "." in key:
            top, leaf = key.split(".", 1)
            if top in FULL_PROFILE and leaf in FULL_PROFILE[top]:
                allowed.setdefault(top, {})[leaf] = FULL_PROFILE[top][leaf]
        elif key in FULL_PROFILE:
            allowed[key] = FULL_PROFILE[key]
    return allowed


SCOPED_PROFILE = _scoped_profile()
VALID_ENTITIES: list[str] = KB.get("valid_entities", []) or ["general"]


# ------------------------- Prompt (verbatim from agent_service.py) -------------------------

def _build_system_prompt_base() -> str:
    entities_str = ", ".join(f'"{e}"' for e in VALID_ENTITIES)

    return f"""{KB['agent_identity']}

ORG POLICY:
{KB['org_policy']}

DOMAIN KNOWLEDGE:
{yaml.safe_dump(KB.get('domain_knowledge', {}), sort_keys=False)}

CURRENT ASSESSMENT REFERENCE:
{yaml.safe_dump(KB.get('current_assessment_for_user_001', {}), sort_keys=False)}

You have access to ONLY this slice of the user's profile:
{yaml.safe_dump(SCOPED_PROFILE, sort_keys=False)}

When you respond, output a JSON object ONLY with this exact shape:

{{
  "claim_text": "<one sentence ASSERTION>",
  "rationale": "<2-3 sentences citing your reasoning>",
  "entity": "<MUST be one of: {entities_str}>",
  "subject_id": "user-001",
  "confidence": <float 0.0 to 1.0>
}}

CRITICAL PHRASING RULES for claim_text:
- Phrase as ASSERTIONS about facts or states, NOT as recommendations.
- WRONG: "I recommend against high-caffeine pre-workouts."
- RIGHT: "High-caffeine pre-workouts are contraindicated for this user."
- WRONG: "Should reduce training volume by 40%."
- RIGHT: "Training volume must be reduced 40% this week."
- WRONG: "Recommend reintroducing barbell squats at 56kg."
- RIGHT: "Barbell back squats at 56kg are appropriate this week."
- The assertion must be falsifiable. Another agent could state the direct negation of it.

You MUST pick `entity` from the listed options above. Do NOT invent new entity names.

Output the JSON object ONLY. No preamble, no markdown fences."""


BASE_SYSTEM_PROMPT = _build_system_prompt_base()


# ------------------------- LangGraph state + nodes -------------------------

class AgentState(TypedDict, total=False):
    # Inputs
    trigger: str
    context: dict | None
    # canon_lookup outputs
    canon_ground_truth: dict
    # respond outputs — the adapter's contract keys
    sample_text: str
    sample_metadata: dict
    # Also surfaced for the /respond HTTP response
    claim_json: dict


# LLM handle (built once at module import, reused per request)
_llm = ChatOpenAI(
    model="gpt-5.4-mini",
    api_key=OPENAI_KEY,
    temperature=0.2,
    model_kwargs={"response_format": {"type": "json_object"}},
)


def _respond_node(state: AgentState) -> AgentState:
    """
    Real LLM call. Injects the canon block ABOVE the base system prompt
    so ground truth is the first thing the model sees.
    """
    gt = state.get(CANON_STATE_KEY, {}) or {}
    canon_block = format_canon_block(gt)

    if canon_block:
        system_prompt = canon_block + "\n\n" + BASE_SYSTEM_PROMPT
    else:
        system_prompt = BASE_SYSTEM_PROMPT

    trigger = state.get("trigger", "")
    context = state.get("context")
    user_msg = f"Trigger: {trigger}"
    if context:
        user_msg += f"\n\nAdditional context:\n{yaml.safe_dump(context, sort_keys=False)}"
    user_msg += "\n\nGenerate your assessment as a single JSON object."

    ai_msg = _llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
    )
    raw = (ai_msg.content or "").strip()

    try:
        claim = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned invalid JSON: {e}; raw={raw[:200]}")

    # Build the sample text in EXACTLY the shape the extraction worker
    # already knows how to consume (matches agent_service._post_claim_to_orqestra).
    sample_text = (
        f"{claim['claim_text']} "
        f"(rationale: {claim['rationale']}) "
        f"[entity: {claim['entity']}, subject: {claim['subject_id']}, "
        f"agent: {AGENT_NAME}]"
    )
    metadata = {
        "agent_name": AGENT_NAME,
        "subject_id": claim["subject_id"],
        "entity_hint": claim["entity"],
        "demo_run": True,
        "canon_declared_entities": [
            n for n, r in gt.items() if r.get("status") == "declared"
        ],
    }

    return {
        SAMPLE_TEXT_KEY: sample_text,
        SAMPLE_METADATA_KEY: metadata,
        "claim_json": claim,
    }


def _build_graph_and_adapter() -> LangGraphAdapter:
    # Sprint 10 measurement toggle. Defaults to True so existing behavior
    # is unchanged; measurement runner flips it to "false" via env.
    canon_env = os.environ.get("ORQESTRA_CANON_ENABLED", "true").strip().lower()
    canon_enabled = canon_env not in ("false", "0", "off", "no")

    print(f"[{AGENT_NAME}] canon_enabled={canon_enabled} (ORQESTRA_CANON_ENABLED={canon_env!r})")

    canon_lookup = canon_lookup_node_factory(
        entities=VALID_ENTITIES,
        api_base=ORQESTRA_API,
        api_token=ORQESTRA_KEY,
        canon_enabled=canon_enabled,
    )
    g = StateGraph(AgentState)
    g.add_node("canon_lookup", canon_lookup)
    g.add_node("respond", _respond_node)
    g.set_entry_point("canon_lookup")
    g.add_edge("canon_lookup", "respond")
    g.add_edge("respond", END)
    graph = g.compile()

    return LangGraphAdapter(
        graph=graph,
        system_id=UUID(ORQESTRA_SYSTEM),
        api_base=ORQESTRA_API,
        api_token=ORQESTRA_KEY,
        agent_name=AGENT_NAME,
    )


ADAPTER = _build_graph_and_adapter()


# ------------------------- FastAPI surface -------------------------

app = FastAPI(title=f"{AGENT_NAME} (langgraph demo agent)")


class TriggerRequest(BaseModel):
    trigger: str
    context: dict | None = None


@app.get("/health")
def health() -> dict:
    canon_env = os.environ.get("ORQESTRA_CANON_ENABLED", "true").strip().lower()
    canon_enabled = canon_env not in ("false", "0", "off", "no")
    return {
        "agent": AGENT_NAME,
        "kb_loaded": bool(KB),
        "scoped_keys": list(SCOPED_PROFILE.keys()),
        "executor": "langgraph",
        "valid_entities": VALID_ENTITIES,
        "canon_enabled": canon_enabled,
    }


@app.post("/respond")
async def respond(req: TriggerRequest) -> dict:
    result = await ADAPTER.arun(
        {"trigger": req.trigger, "context": req.context}
    )
    final = result["final_state"]

    if not result["posted"]:
        raise HTTPException(
            status_code=502,
            detail="Adapter failed to post sample to Orqestra.",
        )

    return {
        "agent": AGENT_NAME,
        "claim": final.get("claim_json"),
        "posted_text": final.get(SAMPLE_TEXT_KEY),
        "canon_ground_truth": final.get(CANON_STATE_KEY, {}),
        "node_events": [e for e in result["node_events"] if e["kind"] == "end"],
        "timestamp": time.time(),
    }