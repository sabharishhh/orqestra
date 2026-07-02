"""Generic agent service for the live demo.

One FastAPI image, configured per-agent via env vars:
  AGENT_NAME       e.g. FitnessAgent
  KB_PATH          e.g. /app/demo/kb/fitness_agent.yaml
  USER_PROFILE     e.g. /app/demo/data/user_profile.yaml
  ORQESTRA_API     e.g. http://api:8000
  ORQESTRA_KEY     e.g. oq-...
  ORQESTRA_SYSTEM  the system UUID this agent posts as
  OPENAI_API_KEY   passthrough

Each agent loads ONLY the slices of user_profile its KB's data_access allows.
That keeps the federation honest — Medical can't see budget, Budget can't
see medical, etc.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

AGENT_NAME = os.environ["AGENT_NAME"]
KB_PATH = os.environ["KB_PATH"]
USER_PROFILE_PATH = os.environ["USER_PROFILE"]
ORQESTRA_API = os.environ["ORQESTRA_API"]
ORQESTRA_KEY = os.environ["ORQESTRA_KEY"]
ORQESTRA_SYSTEM = os.environ["ORQESTRA_SYSTEM"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
PORT = int(os.environ.get("PORT", "8100"))

# Load KB and user profile at startup
with open(KB_PATH) as f:
    KB = yaml.safe_load(f)
with open(USER_PROFILE_PATH) as f:
    FULL_PROFILE = yaml.safe_load(f)


def _scoped_profile() -> dict:
    """Return ONLY the profile slices this agent is allowed to see."""
    access = KB.get("data_access", {}).get("can_read", [])
    allowed: dict[str, Any] = {"subject_id": FULL_PROFILE["subject_id"]}
    for key in access:
        # Support nested dotted access like 'nutrition_profile.current_supplements'
        if "." in key:
            top, leaf = key.split(".", 1)
            if top in FULL_PROFILE and leaf in FULL_PROFILE[top]:
                allowed.setdefault(top, {})[leaf] = FULL_PROFILE[top][leaf]
        elif key in FULL_PROFILE:
            allowed[key] = FULL_PROFILE[key]
    return allowed


SCOPED_PROFILE = _scoped_profile()

oai = OpenAI(api_key=OPENAI_KEY)
app = FastAPI(title=f"{AGENT_NAME} (demo agent)")


class TriggerRequest(BaseModel):
    trigger: str  # human-readable description of why this agent is firing
    context: dict | None = None  # optional extra context (e.g. recent claims)


def _build_system_prompt() -> str:
    valid_entities = KB.get("valid_entities", [])
    entities_str = ", ".join(f'"{e}"' for e in valid_entities) if valid_entities else '"general"'

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

def _call_llm(trigger: str, context: dict | None) -> dict:
    user_msg = f"Trigger: {trigger}"
    if context:
        user_msg += f"\n\nAdditional context:\n{yaml.safe_dump(context, sort_keys=False)}"
    user_msg += "\n\nGenerate your assessment as a single JSON object."

    resp = oai.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"LLM returned invalid JSON: {e}; raw={raw[:200]}")


def _post_claim_to_orqestra(claim: dict) -> str:
    """POST the structured claim to Orqestra /samples as raw text the
    extraction worker will re-process. We pre-build the natural-language
    string so extraction lands on the same fields we already have."""
    text = (
        f"{claim['claim_text']} "
        f"(rationale: {claim['rationale']}) "
        f"[entity: {claim['entity']}, subject: {claim['subject_id']}, "
        f"agent: {AGENT_NAME}]"
    )
    payload = {
        "text": text,
        "metadata": {
            "agent_name": AGENT_NAME,
            "subject_id": claim["subject_id"],
            "entity_hint": claim["entity"],
            "demo_run": True,
        },
    }
    url = f"{ORQESTRA_API}/systems/{ORQESTRA_SYSTEM}/samples"
    headers = {"Authorization": f"Bearer {ORQESTRA_KEY}"}
    with httpx.Client(timeout=10.0) as client:
        r = client.post(url, json=payload, headers=headers)
        if r.status_code not in (200, 202):
            raise HTTPException(status_code=502, detail=f"Orqestra rejected sample: {r.status_code} {r.text[:200]}")
    return text


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
def respond(req: TriggerRequest) -> dict:
    """Fire the agent. Generate a claim, POST it to Orqestra, return both."""
    claim = _call_llm(req.trigger, req.context)
    sample_text = _post_claim_to_orqestra(claim)
    return {
        "agent": AGENT_NAME,
        "claim": claim,
        "posted_text": sample_text,
        "timestamp": time.time(),
    }