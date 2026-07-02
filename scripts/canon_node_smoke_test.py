"""
Sprint 9 Task 3 smoke test.

Builds a two-node LangGraph:
    canon_lookup  →  mock_respond
where mock_respond simply echoes the injected canon block as sample_text.
No real LLM calls — this smoke test validates the WIRING of canon-into-
prompt, not LLM behavior. Real LLM integration comes in Task 4.

Pass criteria:
  - canon_lookup fires and populates state['canon_ground_truth']
  - At least one entity resolves as 'declared' (demo-fitness has 6 declared)
  - format_canon_block produces non-empty output containing at least one
    declared value
  - Adapter posts the sample; claim lands within ~10s
"""
import asyncio
import hashlib
import logging
import secrets
import sys
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import text as sql_text

from core.database import SessionLocal
from models.database import Organization, System
from services.langgraph_adapter import (
    LangGraphAdapter,
    SAMPLE_METADATA_KEY,
    SAMPLE_TEXT_KEY,
)
from demo.agents.graph_nodes import (
    CANON_STATE_KEY,
    canon_lookup_node_factory,
    format_canon_block,
)

logging.basicConfig(level=logging.INFO, format="[canon_node_smoke] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"
DEMO_ORG_SLUG = "demo-fitness"
TARGET_AGENT_NAME = "MedicalAgent"

# Entities MedicalAgent (in the fitness demo) cares about. Two of these
# ARE declared in demo-fitness (activity_limit, sleep_target); the other
# is intentionally unknown to exercise the fail-null path.
MEDICAL_AGENT_ENTITIES = [
    "activity_limit",
    "sleep_target",
    "made_up_entity_that_does_not_exist",
]


class ScratchState(TypedDict, total=False):
    user_message: str
    canon_ground_truth: dict
    sample_text: str
    sample_metadata: dict


def make_mock_respond():
    """
    Mock 'respond' node. Formats the canon block and returns it as
    sample_text. Real Task 4 replaces this with a gpt-5.4-mini call.
    """
    def mock_respond(state: dict) -> dict:
        gt = state.get(CANON_STATE_KEY, {})
        block = format_canon_block(gt)
        user_msg = state.get("user_message", "")
        if block:
            body = (
                f"[MockResponse to '{user_msg}'] Consulted canon:\n{block}"
            )
        else:
            body = (
                f"[MockResponse to '{user_msg}'] No canon available; "
                "answering from prior knowledge only."
            )
        return {
            SAMPLE_TEXT_KEY: body,
            SAMPLE_METADATA_KEY: {
                "smoke_test": "canon_node",
                "declared_entities": [
                    n for n, r in gt.items() if r.get("status") == "declared"
                ],
            },
        }
    return mock_respond


def rotate_agent_token(agent_name: str) -> tuple[str, str]:
    raw = "oq-" + secrets.token_hex(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        if not org:
            raise RuntimeError(f"'{DEMO_ORG_SLUG}' not found — run seed_org first")
        sys_ = db.query(System).filter_by(org_id=org.id, name=agent_name).first()
        if not sys_:
            raise RuntimeError(f"System '{agent_name}' not found in {DEMO_ORG_SLUG}")
        sys_.api_key_hash = hashed
        system_id = sys_.id
        db.commit()
        logger.info(f"Rotated {agent_name} token; system_id={system_id}")
        return raw, str(system_id)
    finally:
        db.close()


def count_claims_for_system(system_id: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            sql_text("SELECT COUNT(*) FROM claims WHERE system_id = :sid"),
            {"sid": system_id},
        ).scalar() or 0
    finally:
        db.close()


async def main():
    token, system_id = rotate_agent_token(TARGET_AGENT_NAME)
    before = count_claims_for_system(system_id)
    logger.info(f"claims before: {before}")

    # Build the graph
    canon_lookup = canon_lookup_node_factory(
        entities=MEDICAL_AGENT_ENTITIES,
        api_base=API_BASE,
        api_token=token,
    )
    respond = make_mock_respond()

    g = StateGraph(ScratchState)
    g.add_node("canon_lookup", canon_lookup)
    g.add_node("respond", respond)
    g.set_entry_point("canon_lookup")
    g.add_edge("canon_lookup", "respond")
    g.add_edge("respond", END)
    graph = g.compile()

    adapter = LangGraphAdapter(
        graph=graph,
        system_id=system_id,
        api_base=API_BASE,
        api_token=token,
        agent_name=TARGET_AGENT_NAME,
    )

    result = await adapter.arun({"user_message": "What are my activity limits?"})

    # --- Assertions ---
    final = result["final_state"]
    gt = final.get(CANON_STATE_KEY, {})
    logger.info(f"canon_ground_truth keys: {list(gt.keys())}")
    for name, row in gt.items():
        logger.info(
            f"  {name:40s} status={row.get('status'):16s} "
            f"value={row.get('value')!r}"
        )

    declared_names = [n for n, r in gt.items() if r.get("status") == "declared"]
    if len(declared_names) < 1:
        logger.error("❌ expected at least 1 declared entity, got 0")
        sys.exit(2)
    logger.info(f"✓ declared entities: {declared_names}")

    block = format_canon_block(gt)
    if not block:
        logger.error("❌ format_canon_block returned empty despite declared entities")
        sys.exit(2)
    if "activity_limit" not in block:
        logger.error(f"❌ canon block missing 'activity_limit'. Block:\n{block}")
        sys.exit(2)
    logger.info("✓ format_canon_block produced non-empty output containing declared values")

    if not result["posted"]:
        logger.error("❌ adapter reported posted=False")
        sys.exit(2)

    for wait in [0.5, 1.0, 2.0, 3.0, 4.0]:
        time.sleep(wait)
        after = count_claims_for_system(system_id)
        if after > before:
            logger.info(f"✅ claim landed after {wait}s wait (before={before}, after={after})")
            return
        logger.info(f"  no new claim yet after {wait}s (count={after})")

    logger.error(f"❌ no claim landed after 10.5s (before={before}, after={after})")
    sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())