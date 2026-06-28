import logging
from observability import get_logger
from sqlalchemy.orm import Session
from models.database import Claim

logger = get_logger(__name__)

def compute_lca(db: Session, claim_a_id: str, claim_b_id: str) -> dict:
    """
    Computes the Lowest Common Ancestor (LCA) between two claims.
    Walks up the parent_claim_id chain to find the exact fork point.
    """
    def get_lineage(start_id):
        lineage = {}
        current_id = start_id
        dist = 0
        
        # F1.3 Compliance: LCA depth cap of 100 to prevent infinite recursion
        while current_id and dist < 100:
            lineage[str(current_id)] = dist
            claim = db.query(Claim).filter(Claim.id == current_id).first()
            
            if not claim or not claim.parent_claim_id:
                break
                
            current_id = claim.parent_claim_id
            dist += 1
            
        return lineage

    lineage_a = get_lineage(claim_a_id)
    lineage_b = get_lineage(claim_b_id)

    # Find where the two ancestral paths intersect
    shared_ancestors = set(lineage_a.keys()).intersection(set(lineage_b.keys()))

    if not shared_ancestors:
        return {
            "has_shared_ancestor": False,
            "lca_claim_id": None,
            "fork_distance_a": len(lineage_a),
            "fork_distance_b": len(lineage_b)
        }

    # The LCA is the shared ancestor with the shortest distance to the current claims
    lca_id = min(shared_ancestors, key=lambda x: lineage_a[x])

    return {
        "has_shared_ancestor": True,
        "lca_claim_id": lca_id,
        "fork_distance_a": lineage_a[lca_id],
        "fork_distance_b": lineage_b[lca_id]
    }