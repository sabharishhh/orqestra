"""
Blast-Radius Dollar Report API.

For any open contradiction, computes the total dollar exposure across
its descendant claim subtree. The graph is traversed via Claim.parent_claim_id
ancestry, scoped strictly to the contradiction's org_id.

Cost math:
    blast_radius = root_cost + sum over descendants of:
                       per_entity_cost * decay^depth

Per-entity costs come from canonical_entities (cost_high_usd) so each
descendant is weighted by its OWN entity's risk profile — a workout_routine
descendant contributes $1,200, a contraindication descendant contributes $50K.
Decay factor is per-org (DetectionConfig.blast_radius_decay).

Read-only. No mutations. The root claim is always at depth 0 and contributes
its full cost; each descendant level multiplies cost by decay^depth.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from api.auth import verify_api_key
from core.database import get_db
from models.database import (
    Contradiction,
    Claim,
    System,
    CanonicalEntity,
)
from services.config_loader import get_org_config

logger = logging.getLogger(__name__)
router = APIRouter()


# Max depth to walk. Defensive cap against pathological graphs.
MAX_DEPTH = 20


def _walk_descendants(db: Session, root_claim_id: str, org_id: str) -> list[dict]:
    """
    Returns all descendants of a root claim (inclusive of the root at depth 0)
    via Claim.parent_claim_id chains, scoped to org_id.

    Order: DFS by depth, deterministic by claim_id within a depth.
    """
    query = sql_text("""
        WITH RECURSIVE descendants AS (
            SELECT
                c.id           AS claim_id,
                c.parent_claim_id,
                c.entity_hint,
                c.subject,
                c.predicate,
                c.object,
                c.system_id,
                c.org_id,
                c.extracted_at,
                0              AS depth
            FROM claims c
            WHERE c.id = CAST(:root_id AS uuid)
              AND c.org_id = CAST(:org_id AS uuid)
            UNION ALL
            SELECT
                child.id,
                child.parent_claim_id,
                child.entity_hint,
                child.subject,
                child.predicate,
                child.object,
                child.system_id,
                child.org_id,
                child.extracted_at,
                d.depth + 1
            FROM claims child
            JOIN descendants d ON child.parent_claim_id = d.claim_id
            WHERE child.org_id = d.org_id
              AND d.depth < :max_depth
        )
        SELECT
            d.claim_id,
            d.parent_claim_id,
            d.entity_hint,
            d.subject,
            d.predicate,
            d.object,
            d.system_id,
            d.depth,
            d.extracted_at,
            s.name AS system_name
        FROM descendants d
        LEFT JOIN systems s ON s.id = d.system_id
        ORDER BY d.depth, d.claim_id;
    """)
    rows = db.execute(query, {
        "root_id":  root_claim_id,
        "org_id":   org_id,
        "max_depth": MAX_DEPTH,
    }).all()

    return [
        {
            "claim_id":         str(r.claim_id),
            "parent_claim_id":  str(r.parent_claim_id) if r.parent_claim_id else None,
            "entity_hint":      r.entity_hint,
            "claim_text":       f"{r.subject} {r.predicate} {r.object}",
            "system_id":        str(r.system_id) if r.system_id else None,
            "system_name":      r.system_name,
            "depth":            r.depth,
            "extracted_at":     r.extracted_at.isoformat() if r.extracted_at else None,
        }
        for r in rows
    ]


def _entity_cost_lookup(db: Session, org_id: str) -> dict[str, int]:
    """
    Returns {canonical_name: cost_high_usd} for the org. Used to weight
    each descendant by its own entity's exposure. Falls back to a sensible
    default when an entity_hint isn't in the canonical vocabulary (orphan
    or auto-induced).
    """
    rows = (
        db.query(CanonicalEntity.canonical_name, CanonicalEntity.cost_high_usd)
          .filter_by(org_id=org_id)
          .all()
    )
    return {name: cost for name, cost in rows}


def _build_tree(nodes: list[dict], root_id: str) -> dict:
    """Convert a flat depth-ordered list into a nested tree rooted at root_id."""
    by_id = {n["claim_id"]: {**n, "children": []} for n in nodes}
    root = by_id.get(root_id)
    if root is None:
        return {}
    for node in nodes:
        if node["claim_id"] == root_id:
            continue
        parent_id = node["parent_claim_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(by_id[node["claim_id"]])
    return root


def _compute_side_blast(
    nodes: list[dict],
    entity_costs: dict[str, int],
    decay: float,
    fallback_cost: int,
) -> tuple[int, list[dict]]:
    """
    For one side of a contradiction, compute the per-node dollar contribution
    and total blast for that side.

    Each node's contribution = entity_cost * decay^depth
    """
    annotated = []
    total = 0
    for n in nodes:
        per_entity = entity_costs.get(n["entity_hint"], fallback_cost)
        contribution = int(round(per_entity * (decay ** n["depth"])))
        total += contribution
        annotated.append({
            **n,
            "per_entity_cost": per_entity,
            "depth_decay":     round(decay ** n["depth"], 4),
            "contribution":    contribution,
        })
    return total, annotated


# =====================================================
# GET /contradictions/{id}/blast-radius
# =====================================================
@router.get("/{contradiction_id}/blast-radius")
def get_blast_radius(
    contradiction_id: UUID,
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Return the total dollar blast-radius of a contradiction across its
    descendant claim subtree. Auth-derived org scope ensures a caller
    cannot query contradictions outside their tenant.
    """
    contra = db.query(Contradiction).filter_by(id=contradiction_id).first()
    if contra is None:
        raise HTTPException(status_code=404, detail="Contradiction not found.")

    # Tenant boundary — the API caller must belong to the same org as the contradiction
    org_id = str(system.org_id)
    if str(contra.org_id) != org_id:
        # Pretend it doesn't exist rather than leak its existence to other tenants
        raise HTTPException(status_code=404, detail="Contradiction not found.")

    cfg = get_org_config(org_id, db)
    decay = cfg.blast_radius_decay

    entity_costs = _entity_cost_lookup(db, org_id)
    # Fallback when an entity_hint isn't canonical (auto-induced orphan).
    # Use the contradiction's own recorded cost as a reasonable default.
    fallback_cost = contra.cost_usd or 100

    # Walk both sides of the contradiction
    side_a_nodes = _walk_descendants(db, str(contra.claim_a_id), org_id)
    side_b_nodes = _walk_descendants(db, str(contra.claim_b_id), org_id)

    side_a_total, side_a_annotated = _compute_side_blast(
        side_a_nodes, entity_costs, decay, fallback_cost
    )
    side_b_total, side_b_annotated = _compute_side_blast(
        side_b_nodes, entity_costs, decay, fallback_cost
    )

    # Build nested trees (depth 0 is the root, with .children populated)
    tree_a = _build_tree(side_a_annotated, str(contra.claim_a_id))
    tree_b = _build_tree(side_b_annotated, str(contra.claim_b_id))

    return {
        "contradiction_id": str(contra.id),
        "org_id":           org_id,
        "severity":         contra.severity,
        "root_cost_usd":    contra.cost_usd or 0,
        "blast_radius_usd": side_a_total + side_b_total,
        "decay_factor":     decay,
        "descendant_count": (len(side_a_nodes) - 1) + (len(side_b_nodes) - 1),
        "side_a": {
            "root_claim_id":   str(contra.claim_a_id),
            "total_usd":       side_a_total,
            "node_count":      len(side_a_nodes),
            "tree":            tree_a,
        },
        "side_b": {
            "root_claim_id":   str(contra.claim_b_id),
            "total_usd":       side_b_total,
            "node_count":      len(side_b_nodes),
            "tree":            tree_b,
        },
    }