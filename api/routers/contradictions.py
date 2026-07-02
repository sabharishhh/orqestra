from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from core.database import get_db
from models.database import Contradiction, Claim, System
from services.lca_computer import compute_lca
from api.auth import verify_api_key

router = APIRouter()


@router.get("/")
def get_active_contradictions(
    status: str = "open",
    limit: int = 50,
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Live feed of semantic collisions across the caller's org's estate.

    Sprint 8 Task 4: previously unauthenticated and unscoped. Now scoped
    to the caller's org via verify_api_key + org_id filter — the F7.1.A
    hole is closed.
    """
    org_id = system.org_id
    results = []

    contradictions = (
        db.query(Contradiction)
          .filter(
              Contradiction.org_id == org_id,
              Contradiction.status == status,
          )
          .order_by(desc(Contradiction.detected_at))
          .limit(limit)
          .all()
    )

    for c in contradictions:
        # Claims are org-scoped too; the filter is defense-in-depth against a
        # stale contradiction pointing at a cross-org claim.
        claim_a = (
            db.query(Claim)
              .filter(Claim.id == c.claim_a_id, Claim.org_id == org_id)
              .first()
        )
        claim_b = (
            db.query(Claim)
              .filter(Claim.id == c.claim_b_id, Claim.org_id == org_id)
              .first()
        )

        if not claim_a or not claim_b:
            continue

        sys_a = (
            db.query(System)
              .filter(System.id == claim_a.system_id, System.org_id == org_id)
              .first()
        )
        sys_b = (
            db.query(System)
              .filter(System.id == claim_b.system_id, System.org_id == org_id)
              .first()
        )

        lca_data = compute_lca(db, c.claim_a_id, c.claim_b_id)

        results.append({
            "id": c.id,
            "severity": c.severity,
            "entity_hint": claim_a.entity_hint,
            "nli_score": c.nli_score,
            "detected_at": c.detected_at,
            "lca_claim_id": lca_data["lca_claim_id"],
            "fork_distance_a": lca_data["fork_distance_a"],
            "fork_distance_b": lca_data["fork_distance_b"],
            "has_shared_ancestor": lca_data["has_shared_ancestor"],
            "system_a": {
                "name": sys_a.name if sys_a else "Unknown",
                "claim": f"{claim_a.subject} {claim_a.predicate} {claim_a.object}",
            },
            "system_b": {
                "name": sys_b.name if sys_b else "Unknown",
                "claim": f"{claim_b.subject} {claim_b.predicate} {claim_b.object}",
            },
        })

    return results


@router.get("/{contradiction_id}/lineage")
def get_contradiction_lineage(
    contradiction_id: str,
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    ReactFlow node schema for a given contradiction, org-scoped.

    Sprint 8 Task 4: cross-org access returns 404 (not 403) — we do not
    leak the existence of a contradiction in another org.
    """
    org_id = system.org_id

    contra = (
        db.query(Contradiction)
          .filter(
              Contradiction.id == contradiction_id,
              Contradiction.org_id == org_id,
          )
          .first()
    )
    if not contra:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    claim_a = (
        db.query(Claim)
          .filter(Claim.id == contra.claim_a_id, Claim.org_id == org_id)
          .first()
    )
    claim_b = (
        db.query(Claim)
          .filter(Claim.id == contra.claim_b_id, Claim.org_id == org_id)
          .first()
    )
    if not claim_a or not claim_b:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    sys_a = (
        db.query(System)
          .filter(System.id == claim_a.system_id, System.org_id == org_id)
          .first()
    )
    sys_b = (
        db.query(System)
          .filter(System.id == claim_b.system_id, System.org_id == org_id)
          .first()
    )

    lca_data = compute_lca(db, contra.claim_a_id, contra.claim_b_id)

    return {
        "has_shared_ancestor": lca_data["has_shared_ancestor"],
        "fork_distance_a": lca_data["fork_distance_a"],
        "fork_distance_b": lca_data["fork_distance_b"],
        "nodes": [
            {"id": "root", "type": "agentNode", "position": {"x": 300, "y": 50},
             "data": {"agentName": "System Core"}},
            {"id": "anc_a", "type": "claimNode", "position": {"x": 50, "y": 200},
             "data": {"entityHint": claim_a.entity_hint,
                      "claimText": f"{claim_a.subject} {claim_a.predicate} {claim_a.object}"}},
            {"id": "anc_b", "type": "claimNode", "position": {"x": 450, "y": 200},
             "data": {"entityHint": claim_b.entity_hint,
                      "claimText": f"{claim_b.subject} {claim_b.predicate} {claim_b.object}"}},
            {"id": "agent_a", "type": "agentNode", "position": {"x": 100, "y": 400},
             "data": {"agentName": sys_a.name if sys_a else "Unknown"}},
            {"id": "agent_b", "type": "agentNode", "position": {"x": 500, "y": 400},
             "data": {"agentName": sys_b.name if sys_b else "Unknown"}},
        ],
        "edges": [
            {"id": "e1", "source": "root", "target": "anc_a", "animated": True,
             "style": {"stroke": "#475569", "strokeWidth": 2}},
            {"id": "e2", "source": "root", "target": "anc_b", "animated": True,
             "style": {"stroke": "#475569", "strokeWidth": 2}},
            {"id": "e3", "source": "anc_a", "target": "agent_a",
             "markerEnd": {"type": "arrowclosed"},
             "style": {"stroke": "#3B82F6", "strokeWidth": 2}},
            {"id": "e4", "source": "anc_b", "target": "agent_b",
             "markerEnd": {"type": "arrowclosed"},
             "style": {"stroke": "#3B82F6", "strokeWidth": 2}},
            {"id": "e5", "source": "agent_a", "target": "agent_b", "animated": True,
             "style": {"stroke": "#EF4444", "strokeWidth": 3, "strokeDasharray": "5,5"},
             "label": "CONTRADICTION",
             "labelStyle": {"fill": "#EF4444", "fontWeight": 700},
             "labelBgStyle": {"fill": "#0B1120"}},
        ],
    }