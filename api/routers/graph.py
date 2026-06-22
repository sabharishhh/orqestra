from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from models.database import System, Claim, Contradiction

router = APIRouter()

@router.get("/")
def get_graph_data(db: Session = Depends(get_db)):
    """Extracts the entire SCCG topology for the 3D visualizer."""
    nodes = []
    links = []
    
    # 1. Render the Systems (The massive central gravity nodes)
    systems = db.query(System).all()
    for sys in systems:
        nodes.append({
            "id": str(sys.id),
            "name": sys.name,
            "group": "system",
            "val": 30 # Mass/Size of the node
        })
        
    # 2. Render the Claims (The orbiting facts)
    claims = db.query(Claim).all()
    for claim in claims:
        nodes.append({
            "id": str(claim.id),
            "name": f"[{claim.entity_hint}] {claim.subject} {claim.predicate} {claim.object}",
            "group": "claim",
            "val": 5 # Smaller mass for individual claims
        })
        
        # Draw the ownership link from System to Claim
        links.append({
            "source": str(claim.system_id),
            "target": str(claim.id),
            "type": "ownership"
        })
        
    # 3. Render the Contradictions (The red collision lasers)
    contradictions = db.query(Contradiction).all()
    for contra in contradictions:
        links.append({
            "source": str(contra.claim_a_id),
            "target": str(contra.claim_b_id),
            "type": "contradiction",
            "severity": contra.severity
        })
        
    return {"nodes": nodes, "links": links}