from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.database import get_db
# ADDED Entity to the imports
from models.database import System, Claim, Contradiction, Entity 

router = APIRouter()

@router.get("/")
def get_graph_data(db: Session = Depends(get_db)):
    """Extracts the entire tri-partite SCCG topology for the 3D visualizer."""
    nodes = []
    links = []
    
    # 1. Render the Systems (The massive central gravity nodes)
    systems = db.query(System).all()
    for sys in systems:
        nodes.append({
            "id": str(sys.id),
            "name": sys.name,
            "group": "system",
            "val": 30
        })
        
    # 2. Render the Entities (The canonical organizational concepts)
    entities = db.query(Entity).all()
    for ent in entities:
        nodes.append({
            "id": str(ent.id),
            "name": ent.canonical_name,
            "group": "entity",
            "val": 20
        })
        
    # 3. Render the Claims (The orbiting facts)
    claims = db.query(Claim).all()
    for claim in claims:
        nodes.append({
            "id": str(claim.id),
            "name": f"[{claim.entity_hint}] {claim.subject} {claim.predicate} {claim.object}",
            "group": "claim",
            "val": 5
        })
        
        # Draw the ownership link from System -> Claim
        links.append({
            "source": str(claim.system_id),
            "target": str(claim.id),
            "type": "ownership"
        })
        
        # Draw the semantic link from Claim -> Entity (if it has been assigned!)
        if claim.entity_id:
            links.append({
                "source": str(claim.id),
                "target": str(claim.entity_id),
                "type": "about"
            })
        
    # 4. Render the Contradictions (The red collision lasers)
    contradictions = db.query(Contradiction).filter(Contradiction.status == "open").all()
    for contra in contradictions:
        links.append({
            "source": str(contra.claim_a_id),
            "target": str(contra.claim_b_id),
            "type": "contradiction",
            "severity": contra.severity
        })
        
    return {"nodes": nodes, "links": links}