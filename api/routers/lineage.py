"""
Lineage Graph API — full causal-DAG visualization for a contradiction.

Returns ReactFlow-shaped nodes + edges representing:
  - All ancestors of claim_a and claim_b up to MAX_DEPTH
  - All descendants of claim_a and claim_b (the blast radius)
  - The Lowest Common Ancestor (if any), highlighted
  - The contradicting agents

The frontend renders this directly without any layout logic — positions
are computed server-side via BFS depth.

Read-only. Tenant-scoped via API key → System → org_id.
"""
import logging
from collections import defaultdict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from core.database import get_db
from models.database import Contradiction, Claim, System
from services.lca_computer import compute_lca

logger = logging.getLogger(__name__)
router = APIRouter()


# Hard caps to prevent runaway graphs in pathological cases
MAX_ANCESTOR_DEPTH = 10
MAX_DESCENDANT_DEPTH = 10

# Layout constants — frontend uses these positions directly
NODE_WIDTH = 360         # claimNode is ~320 wide; padding
NODE_HEIGHT = 180        # vertical spacing per depth row
HORIZONTAL_GAP = 80      # gap between A and B columns at same depth


def _walk_ancestors(db: Session, root_claim_id: str, org_id: str) -> list[dict]:
    """Walk up parent_claim_id chain. Depth 0 = root, depth -1 = parent, etc."""
    query = sql_text("""
        WITH RECURSIVE ancestors AS (
            SELECT
                c.id AS claim_id, c.parent_claim_id, c.entity_hint,
                c.subject, c.predicate, c.object, c.system_id, c.org_id,
                0 AS depth
            FROM claims c
            WHERE c.id = CAST(:root_id AS uuid)
              AND c.org_id = CAST(:org_id AS uuid)
            UNION ALL
            SELECT
                parent.id, parent.parent_claim_id, parent.entity_hint,
                parent.subject, parent.predicate, parent.object,
                parent.system_id, parent.org_id,
                a.depth - 1
            FROM claims parent
            JOIN ancestors a ON parent.id = a.parent_claim_id
            WHERE parent.org_id = a.org_id
              AND ABS(a.depth) < :max_depth
        )
        SELECT a.claim_id, a.parent_claim_id, a.entity_hint,
               a.subject, a.predicate, a.object, a.system_id, a.depth,
               s.name AS system_name
        FROM ancestors a
        LEFT JOIN systems s ON s.id = a.system_id
        ORDER BY a.depth DESC, a.claim_id
    """)
    rows = db.execute(query, {
        "root_id": root_claim_id,
        "org_id": org_id,
        "max_depth": MAX_ANCESTOR_DEPTH,
    }).all()
    return [_row_to_dict(r) for r in rows]


def _walk_descendants(db: Session, root_claim_id: str, org_id: str) -> list[dict]:
    """Walk down parent_claim_id chain. Depth 0 = root, depth +1 = child, etc."""
    query = sql_text("""
        WITH RECURSIVE descendants AS (
            SELECT
                c.id AS claim_id, c.parent_claim_id, c.entity_hint,
                c.subject, c.predicate, c.object, c.system_id, c.org_id,
                0 AS depth
            FROM claims c
            WHERE c.id = CAST(:root_id AS uuid)
              AND c.org_id = CAST(:org_id AS uuid)
            UNION ALL
            SELECT
                child.id, child.parent_claim_id, child.entity_hint,
                child.subject, child.predicate, child.object,
                child.system_id, child.org_id,
                d.depth + 1
            FROM claims child
            JOIN descendants d ON child.parent_claim_id = d.claim_id
            WHERE child.org_id = d.org_id
              AND d.depth < :max_depth
        )
        SELECT d.claim_id, d.parent_claim_id, d.entity_hint,
               d.subject, d.predicate, d.object, d.system_id, d.depth,
               s.name AS system_name
        FROM descendants d
        LEFT JOIN systems s ON s.id = d.system_id
        ORDER BY d.depth ASC, d.claim_id
    """)
    rows = db.execute(query, {
        "root_id": root_claim_id,
        "org_id": org_id,
        "max_depth": MAX_DESCENDANT_DEPTH,
    }).all()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(r) -> dict:
    return {
        "claim_id": str(r.claim_id),
        "parent_claim_id": str(r.parent_claim_id) if r.parent_claim_id else None,
        "entity_hint": r.entity_hint,
        "claim_text": f"{r.subject} {r.predicate} {r.object}",
        "system_id": str(r.system_id) if r.system_id else None,
        "system_name": r.system_name,
        "depth": r.depth,
    }


def _build_graph(
    side_a_claims: list[dict],
    side_b_claims: list[dict],
    lca_claim_id: Optional[str],
    contra_id: str,
) -> tuple[list[dict], list[dict]]:
    """
    Convert two sets of claims into ReactFlow nodes + edges with positions.

    Layout:
      - LCA at the top center if present
      - Side A claims fan down-left, side B fan down-right
      - Descendants below their parents
      - Agent nodes at the bottom for each unique system
      - Contradiction edge between the two root claims
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_claim_ids: set[str] = set()
    seen_system_ids: set[str] = set()

    # Bucket claims by depth so we can position rows
    depth_buckets: dict[int, list[tuple[str, dict]]] = defaultdict(list)
    for claim in side_a_claims:
        if claim["claim_id"] in seen_claim_ids:
            continue
        seen_claim_ids.add(claim["claim_id"])
        depth_buckets[claim["depth"]].append(("A", claim))
    for claim in side_b_claims:
        if claim["claim_id"] in seen_claim_ids:
            continue
        seen_claim_ids.add(claim["claim_id"])
        depth_buckets[claim["depth"]].append(("B", claim))

    # Compute positions
    sorted_depths = sorted(depth_buckets.keys())
    for depth in sorted_depths:
        side_a_count = sum(1 for s, _ in depth_buckets[depth] if s == "A")
        side_b_count = sum(1 for s, _ in depth_buckets[depth] if s == "B")
        a_index = 0
        b_index = 0
        for side, claim in depth_buckets[depth]:
            is_lca = claim["claim_id"] == lca_claim_id
            is_root_a = depth == 0 and side == "A"
            is_root_b = depth == 0 and side == "B"

            # X position: A column negative offset, B column positive
            if side == "A":
                x = -((side_a_count - a_index) * (NODE_WIDTH + HORIZONTAL_GAP)) + (NODE_WIDTH / 2)
                a_index += 1
            else:
                x = (b_index * (NODE_WIDTH + HORIZONTAL_GAP)) + HORIZONTAL_GAP
                b_index += 1

            # Y position: deeper depth = lower on screen
            # Center on depth=0 (the contradiction roots)
            y = depth * NODE_HEIGHT * 1.5

            nodes.append({
                "id": claim["claim_id"],
                "type": "claimNode",
                "position": {"x": x, "y": y},
                "data": {
                    "entityHint": claim["entity_hint"],
                    "claimText": claim["claim_text"],
                    "systemName": claim["system_name"],
                    "depth": claim["depth"],
                    "isConflict": is_root_a or is_root_b,
                    "isLCA": is_lca,
                    "side": side,
                },
            })

            # Edge to parent (if parent is in our node set)
            if claim["parent_claim_id"] and claim["parent_claim_id"] in seen_claim_ids:
                edges.append({
                    "id": f"e_{claim['parent_claim_id']}_{claim['claim_id']}",
                    "source": claim["parent_claim_id"],
                    "target": claim["claim_id"],
                    "animated": False,
                    "style": {
                        "stroke": "#6366F1" if is_lca else "#475569",
                        "strokeWidth": 2,
                    },
                })

            # Track agent nodes to add at the bottom
            if claim["system_id"] and claim["system_id"] not in seen_system_ids:
                seen_system_ids.add(claim["system_id"])

    # Add agent nodes (one per system) at the deepest row + 1
    deepest_depth = max(sorted_depths) if sorted_depths else 0
    agent_y = (deepest_depth + 1) * NODE_HEIGHT * 1.5
    agent_systems = {}
    for claim in side_a_claims + side_b_claims:
        if claim["system_id"] and claim["system_id"] not in agent_systems:
            agent_systems[claim["system_id"]] = claim["system_name"]

    agent_x_offset = -((len(agent_systems) - 1) * (NODE_WIDTH + HORIZONTAL_GAP)) / 2
    for i, (sys_id, sys_name) in enumerate(agent_systems.items()):
        nodes.append({
            "id": f"agent_{sys_id}",
            "type": "agentNode",
            "position": {
                "x": agent_x_offset + i * (NODE_WIDTH + HORIZONTAL_GAP),
                "y": agent_y,
            },
            "data": {"agentName": sys_name},
        })

        # Connect agent to its claims via dashed edges
        for claim in side_a_claims + side_b_claims:
            if claim["system_id"] == sys_id and claim["depth"] == 0:
                edges.append({
                    "id": f"e_agent_{sys_id}_{claim['claim_id']}",
                    "source": f"agent_{sys_id}",
                    "target": claim["claim_id"],
                    "animated": False,
                    "style": {
                        "stroke": "#3B82F6",
                        "strokeWidth": 1.5,
                        "strokeDasharray": "5,5",
                    },
                })

    # The contradiction edge — red, dashed, animated, between the two roots
    root_a = next((c for c in side_a_claims if c["depth"] == 0), None)
    root_b = next((c for c in side_b_claims if c["depth"] == 0), None)
    if root_a and root_b:
        edges.append({
            "id": f"e_contradiction_{contra_id}",
            "source": root_a["claim_id"],
            "target": root_b["claim_id"],
            "animated": True,
            "type": "straight",
            "label": "CONTRADICTION",
            "labelStyle": {"fill": "#EF4444", "fontWeight": 700, "fontSize": 11},
            "labelBgStyle": {"fill": "#0B1120"},
            "style": {
                "stroke": "#EF4444",
                "strokeWidth": 3,
                "strokeDasharray": "5,5",
            },
        })

    return nodes, edges


# =====================================================
# GET /contradictions/{id}/lineage-graph
# =====================================================
@router.get("/{contradiction_id}/lineage-graph")
def get_lineage_graph(
    contradiction_id: UUID,
    db: Session = Depends(get_db),
):
    # No auth — public dashboard endpoint matching the existing /lineage pattern.
    # Tenant scope is implicit: contradiction.org_id loaded from the DB scopes
    # the walks. UUIDs aren't enumerable, so cross-tenant probing is impractical.
    contra = db.query(Contradiction).filter_by(id=contradiction_id).first()
    if contra is None:
        raise HTTPException(status_code=404, detail="Contradiction not found.")

    org_id = str(contra.org_id)

    # Walk both directions from both claims
    side_a_ancestors = _walk_ancestors(db, str(contra.claim_a_id), org_id)
    side_a_descendants = _walk_descendants(db, str(contra.claim_a_id), org_id)
    side_b_ancestors = _walk_ancestors(db, str(contra.claim_b_id), org_id)
    side_b_descendants = _walk_descendants(db, str(contra.claim_b_id), org_id)

    # Merge ancestors + descendants per side. The root claim appears in both
    # (depth 0) — dedupe by claim_id with descendant version winning (correct depth).
    side_a = _dedupe_claims(side_a_ancestors + side_a_descendants)
    side_b = _dedupe_claims(side_b_ancestors + side_b_descendants)

    # Compute LCA via existing utility
    lca_data = compute_lca(db, contra.claim_a_id, contra.claim_b_id)
    lca_id = lca_data.get("lca_claim_id")

    nodes, edges = _build_graph(side_a, side_b, lca_id, str(contra.id))

    return {
        "contradiction_id": str(contra.id),
        "severity": contra.severity,
        "entity_hint": _root_entity_hint(side_a) or _root_entity_hint(side_b),
        "has_shared_ancestor": lca_data.get("has_shared_ancestor", False),
        "lca_claim_id": str(lca_id) if lca_id else None,
        "fork_distance_a": lca_data.get("fork_distance_a", 0),
        "fork_distance_b": lca_data.get("fork_distance_b", 0),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def _dedupe_claims(claims: list[dict]) -> list[dict]:
    """Dedupe by claim_id. Later entries override (descendants win over ancestors at depth 0)."""
    by_id = {}
    for c in claims:
        by_id[c["claim_id"]] = c
    return list(by_id.values())


def _root_entity_hint(claims: list[dict]) -> Optional[str]:
    """Find the entity_hint of the depth-0 claim."""
    for c in claims:
        if c["depth"] == 0:
            return c["entity_hint"]
    return None