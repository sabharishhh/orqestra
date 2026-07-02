"""
services/langgraph_adapter.py — Sprint 9 core.

Runs a LangGraph agent, observes execution, posts the final sample to
Orqestra. One adapter instance per agent container (per-agent, not
per-request; per-request state lives in the graph's input_state).

Design shape:
- Wraps a pre-compiled StateGraph; caller owns graph design.
- Runs via astream_events(version="v2") — the surface the provenance
  probe validated in the pre-Sprint-9 spike.
- Enforces a claim contract: the graph's final state MUST have a
  'sample_text' field. Optional 'sample_metadata' rides alongside.
- Posts one sample per run to POST /systems/{system_id}/samples with
  the caller-provided parent_claim_id (None = standalone, no parent).

Not in Sprint 9:
- Per-node claim emission (multi-sample per run driven by the
  topology map). The map is built but unused. Ready for Sprint 10+.
- Pre-answer Canon lookup — that lives in the GRAPH as its own node.
  The adapter stays purely observational.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import httpx

from observability import get_logger, timed

logger = get_logger(__name__)


SAMPLE_TEXT_KEY = "sample_text"
SAMPLE_METADATA_KEY = "sample_metadata"


class LangGraphAdapter:
    """
    Observes a LangGraph run and posts the produced sample to Orqestra.

    The graph's contract:
        - Input state is whatever the graph author defines.
        - Final state MUST include SAMPLE_TEXT_KEY (a string).
        - Final state MAY include SAMPLE_METADATA_KEY (a dict).

    Usage:
        adapter = LangGraphAdapter(
            graph=compiled_state_graph,
            system_id=uuid.UUID("..."),
            api_base="http://api:8000",
            api_token="oq-...",
            agent_name="MedicalAgent",
        )
        result = await adapter.arun({"user_message": "..."})
    """

    def __init__(
        self,
        graph: Any,             # A compiled StateGraph. Annotated Any to survive langgraph API drift.
        system_id: UUID,
        api_base: str,
        api_token: str,
        agent_name: str,
    ):
        self.graph = graph
        self.system_id = system_id
        self.api_base = api_base.rstrip("/")
        self.api_token = api_token
        self.agent_name = agent_name

        # Precompute predecessor map. Unused in Sprint 9 (single-sample per run)
        # but built here so future per-node emission doesn't need to rebuild it.
        self.topology: dict[str, list[str]] = self._build_topology()
        logger.info(
            "adapter.initialized",
            agent=agent_name,
            system_id=str(system_id),
            topology_nodes=list(self.topology.keys()),
        )

    # ------------------------------------------------------------------
    # Topology map (validated by the pre-Sprint-9 provenance probe)
    # ------------------------------------------------------------------
    def _build_topology(self) -> dict[str, list[str]]:
        """
        Predecessor map: {node_name: [predecessor_node_names]}.
        Excludes LangGraph's pseudo-nodes ('__start__', '__end__') so the
        adapter only counts author-declared nodes.
        """
        try:
            g = self.graph.get_graph()
        except Exception as e:
            logger.warning("adapter.topology_get_graph_failed", error=str(e))
            return {}

        try:
            raw_nodes = list(getattr(g, "nodes", []))
        except Exception:
            raw_nodes = []

        # Filter out LangGraph internals — they surface as pseudo-nodes but
        # are not author-declared and shouldn't count as claim-emission points.
        def _is_pseudo(name: str) -> bool:
            return name.startswith("__") and name.endswith("__")

        node_names = [n for n in raw_nodes if not _is_pseudo(n)]
        topo: dict[str, list[str]] = {n: [] for n in node_names}

        try:
            edges = list(getattr(g, "edges", []))
        except Exception:
            edges = []

        for edge in edges:
            src = getattr(edge, "source", None)
            tgt = getattr(edge, "target", None)
            if src is None or tgt is None:
                try:
                    src, tgt = edge[0], edge[1]
                except Exception:
                    continue
            if _is_pseudo(src) or _is_pseudo(tgt):
                continue
            topo.setdefault(tgt, []).append(src)

        return topo

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    async def arun(
        self,
        input_state: dict,
        parent_claim_id: Optional[UUID] = None,
    ) -> dict:
        """
        Execute the graph, observe events, post the final sample.

        Returns:
            {
              "final_state": <the graph's final state dict>,
              "node_events": [{"kind": "start"|"end", "node": str, "run_id": str}, ...],
              "posted": bool,
            }
        """
        node_events: list[dict] = []
        final_state: Optional[dict] = None

        async for ev in self.graph.astream_events(input_state, version="v2"):
            etype = ev.get("event", "")
            name = ev.get("name", "")

            # Track only nodes we declared in the graph — not the wrapping
            # "LangGraph" event or LLM/tool sub-events.
            if name in self.topology:
                if etype == "on_chain_start":
                    node_events.append({
                        "kind": "start",
                        "node": name,
                        "run_id": str(ev.get("run_id", "")),
                    })
                elif etype == "on_chain_end":
                    node_events.append({
                        "kind": "end",
                        "node": name,
                        "run_id": str(ev.get("run_id", "")),
                    })

            # The graph's own end event carries the final aggregated state.
            # `name` here is the compiled graph's name — typically "LangGraph"
            # unless the graph was compiled with a custom name.
            if etype == "on_chain_end" and name not in self.topology:
                output = (ev.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output

        if final_state is None:
            raise RuntimeError(
                f"{self.agent_name}: LangGraph run finished but no final state was observed. "
                "astream_events emitted no top-level on_chain_end with an output dict."
            )

        # ------ Claim contract ------
        sample_text = final_state.get(SAMPLE_TEXT_KEY)
        if not sample_text or not isinstance(sample_text, str):
            logger.warning(
                "adapter.no_sample_emitted",
                agent=self.agent_name,
                final_state_keys=list(final_state.keys()),
                sample_text_type=type(sample_text).__name__,
            )
            return {
                "final_state": final_state,
                "node_events": node_events,
                "posted": False,
            }

        # Metadata: caller-provided plus what the adapter knows.
        raw_meta = final_state.get(SAMPLE_METADATA_KEY) or {}
        sample_metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        sample_metadata["origin"] = "langgraph_adapter"
        sample_metadata["agent_name"] = self.agent_name
        sample_metadata["node_trace"] = [
            e["node"] for e in node_events if e["kind"] == "end"
        ]

        # ------ Post ------
        with timed("adapter.post_sample", agent=self.agent_name) as ctx:
            posted = await self._post_sample(
                text=sample_text,
                metadata=sample_metadata,
                parent_claim_id=parent_claim_id,
            )
            ctx["posted"] = posted

        return {
            "final_state": final_state,
            "node_events": node_events,
            "posted": posted,
        }

    # ------------------------------------------------------------------
    # HTTP post
    # ------------------------------------------------------------------
    async def _post_sample(
        self,
        text: str,
        metadata: dict,
        parent_claim_id: Optional[UUID],
    ) -> bool:
        url = f"{self.api_base}/systems/{self.system_id}/samples"
        payload: dict = {"text": text, "metadata": metadata}
        if parent_claim_id is not None:
            payload["parent_claim_id"] = str(parent_claim_id)

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            logger.error(
                "adapter.post_transport_error",
                agent=self.agent_name,
                url=url,
                error=str(e),
            )
            return False

        if r.status_code != 202:
            logger.error(
                "adapter.post_rejected",
                agent=self.agent_name,
                status_code=r.status_code,
                body=r.text[:400],
            )
            return False

        logger.info(
            "adapter.sample_posted",
            agent=self.agent_name,
            system_id=str(self.system_id),
            parent_claim_id=str(parent_claim_id) if parent_claim_id else None,
            text_preview=text[:80],
        )
        return True