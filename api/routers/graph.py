from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from models.database import System, Claim, Contradiction, Entity
from api.auth import verify_api_key

router = APIRouter()


@router.get("/")
def get_graph_data(
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Tri-partite SCCG topology for the caller's org's estate.

    Sprint 8 Task 4: previously returned every system, claim, and
    contradiction globally. Now org-scoped via verify_api_key.

    Note: the legacy `entities` table has no org_id column and is
    effectively dead — no writer populates it. Kept in the response
    for shape compatibility; returns empty in practice.
    """
    org_id = system.org_id
    nodes = []
    links = []

    # 1. Systems (central gravity nodes) — org-scoped
    systems = db.query(System).filter(System.org_id == org_id).all()
    for sys in systems:
        nodes.append({
            "id": str(sys.id),
            "name": sys.name,
            "group": "system",
            "val": 30,
        })

    # 2. Entities (legacy global vocabulary; no org_id column)
    #    Empty in practice; kept for shape.
    entities = db.query(Entity).all()
    for ent in entities:
        nodes.append({
            "id": str(ent.id),
            "name": ent.canonical_name,
            "group": "entity",
            "val": 20,
        })

    # 3. Claims — org-scoped
    claims = db.query(Claim).filter(Claim.org_id == org_id).all()
    for claim in claims:
        nodes.append({
            "id": str(claim.id),
            "name": f"[{claim.entity_hint}] {claim.subject} {claim.predicate} {claim.object}",
            "group": "claim",
            "val": 5,
        })

        links.append({
            "source": str(claim.system_id),
            "target": str(claim.id),
            "type": "ownership",
        })

        if claim.entity_id:
            links.append({
                "source": str(claim.id),
                "target": str(claim.entity_id),
                "type": "about",
            })

    # 4. Open contradictions — org-scoped
    contradictions = (
        db.query(Contradiction)
          .filter(
              Contradiction.org_id == org_id,
              Contradiction.status == "open",
          )
          .all()
    )
    for contra in contradictions:
        links.append({
            "source": str(contra.claim_a_id),
            "target": str(contra.claim_b_id),
            "type": "contradiction",
            "severity": contra.severity,
        })

    return {"nodes": nodes, "links": links}