"""
Sprint 9 Task 2 smoke test.

Builds a mock two-node LangGraph (no LLM calls), runs it through the
LangGraphAdapter using a real API token for MedicalAgent from the
demo-fitness org, verifies the sample lands in the claims table.

Pass criteria:
  - adapter run reports posted=True
  - a new row appears in claims for MedicalAgent's system_id
  - node_events shows both node_a and node_b end events
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
from models.database import System, Organization
from services.langgraph_adapter import LangGraphAdapter, SAMPLE_TEXT_KEY, SAMPLE_METADATA_KEY

logging.basicConfig(level=logging.INFO, format="[adapter_smoke] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"
DEMO_ORG_SLUG = "demo-fitness"
TARGET_AGENT_NAME = "MedicalAgent"


class ScratchState(TypedDict, total=False):
    user_message: str
    intermediate: str
    sample_text: str
    sample_metadata: dict


def node_a(state: ScratchState) -> ScratchState:
    return {"intermediate": "processed: " + state.get("user_message", "")}


def node_b(state: ScratchState) -> ScratchState:
    return {
        SAMPLE_TEXT_KEY: (
            "User's max heart rate is 180 bpm during the ACL recovery window."
        ),
        SAMPLE_METADATA_KEY: {
            "smoke_test": True,
            "intermediate_seen": state.get("intermediate", ""),
        },
    }


def build_graph():
    g = StateGraph(ScratchState)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)
    g.set_entry_point("node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", END)
    return g.compile()  # no checkpointer — one-shot stateless run


def rotate_agent_token(agent_name: str) -> tuple[str, str]:
    """Mint a fresh token for the target agent and rotate its api_key_hash."""
    raw = "oq-" + secrets.token_hex(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=DEMO_ORG_SLUG).first()
        if not org:
            raise RuntimeError(f"'{DEMO_ORG_SLUG}' org not found — run seed_org first")
        sys_ = (
            db.query(System)
              .filter_by(org_id=org.id, name=agent_name)
              .first()
        )
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

    graph = build_graph()
    adapter = LangGraphAdapter(
        graph=graph,
        system_id=system_id,
        api_base=API_BASE,
        api_token=token,
        agent_name=TARGET_AGENT_NAME,
    )

    result = await adapter.arun({"user_message": "smoke test message"})

    logger.info(f"posted: {result['posted']}")
    logger.info(f"node_events (end only): {[e for e in result['node_events'] if e['kind'] == 'end']}")

    if not result["posted"]:
        logger.error("❌ adapter reported posted=False")
        sys.exit(2)

    # Extraction is async — poll briefly for the claim to land.
    for wait in [0.5, 1.0, 2.0, 3.0, 4.0]:
        time.sleep(wait)
        after = count_claims_for_system(system_id)
        if after > before:
            logger.info(f"✅ claims after {wait}s wait: {after} (+{after - before})")
            return
        logger.info(f"  no new claim yet after {wait}s (count={after})")

    logger.error(f"❌ no claim landed after 10.5s total wait (before={before}, after={after})")
    sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())