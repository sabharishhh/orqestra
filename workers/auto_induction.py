import os
import json
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from itertools import combinations
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import Claim, InductionCandidate, Entity
from core.celery_app import celery_app
from openai import OpenAI

logger = logging.getLogger(__name__)

def calculate_cosine_distance(emb1, emb2):
    """Safely calculates cosine distance between two raw vector arrays."""
    if emb1 is None or emb2 is None or len(emb1) == 0 or len(emb2) == 0: 
        return 1.0
    a, b = np.array(emb1), np.array(emb2)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0: 
        return 1.0
    return float(1.0 - (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))

def get_claim_text(claim: Claim) -> str:
    """Helper to safely reconstruct the text since claim_text isn't a direct column."""
    return f"{claim.subject} {claim.predicate} {claim.object}"

def llm_suggest_entity_name(representative_claim: str, sample_claims: list) -> dict:
    """Uses LLM to evaluate the cluster and assign a canonical entity identifier."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    prompt = f"""Representative Claim: {representative_claim}
Other Claims in Cluster: {sample_claims}
Provide a short, snake_case canonical name for this concept and classify its type 
(policy, pricing, product, compliance, legal, hr, technical, clinical, general)."""
    
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": "You extract canonical entity names and types. Return strictly JSON: {'name': 'snake_case_name', 'type': 'category'}"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith('```json'): 
        raw = raw[7:-3]
    elif raw.startswith('```'):
        raw = raw[3:-3]
    return json.loads(raw.strip())

@celery_app.task(queue="claim_extraction")
def run_nightly_induction():
    """Worker 5: Unsupervised ontology expansion via Agglomerative Clustering."""
    db: Session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        
        # 1. Fetch orphaned claims generated in the last 7 days
        unassigned = db.query(Claim).filter(Claim.entity_id == None, Claim.extracted_at >= cutoff).all()
        if len(unassigned) < 5:
            return

        embeddings = np.array([c.embedding for c in unassigned if c.embedding is not None and len(c.embedding) > 0])
        if len(embeddings) < 5:
            return

        # 2. Primary Clustering Pass (0.35 Threshold)
        clustering = AgglomerativeClustering(
            n_clusters=None, 
            distance_threshold=0.35, 
            metric="cosine", 
            linkage="average"
        )
        labels = clustering.fit_predict(embeddings)

        clusters = {}
        for claim, label in zip(unassigned, labels):
            clusters.setdefault(label, []).append(claim)

        processed_centroids = []
        
        for cluster_id, cluster_claims in clusters.items():
            if len(cluster_claims) < 5:
                continue

            cluster_embeddings = np.array([c.embedding for c in cluster_claims])
            centroid = cluster_embeddings.mean(axis=0)
            
            # 3. F6.1 Mitigation: Second-Pass Merge for Overlapping Entities
            is_duplicate = False
            for pc in processed_centroids:
                if calculate_cosine_distance(centroid, pc) < 0.20:
                    is_duplicate = True
                    break
            
            if is_duplicate:
                continue
                
            processed_centroids.append(centroid)

            # 4. Find the mathematical center of the cluster (Representative Claim)
            distances = [calculate_cosine_distance(e, centroid) for e in cluster_embeddings]
            representative = cluster_claims[np.argmax(distances)]

            # 5. LLM Canonical Naming
            try:
                # FIX: Replaced .claim_text with the string formatter helper
                suggestion = llm_suggest_entity_name(
                    get_claim_text(representative),
                    [get_claim_text(c) for c in cluster_claims[:5]]
                )
                name_suggestion = suggestion.get("name", "unknown_entity")
                suggested_type = suggestion.get("type", "general")
            except Exception as e:
                logger.error(f"Failed to generate entity name: {e}")
                continue

            # Prevent collisions with existing graph nodes
            existing = db.query(Entity).filter(Entity.canonical_name == name_suggestion).first()
            if existing:
                continue

            # 6. Calculate Organizational Variance Score
            unique_systems = list({c.system_id for c in cluster_claims})
            variance_score = 0.0
            if len(unique_systems) > 1:
                system_centroids = [
                    cluster_embeddings[[i for i, c in enumerate(cluster_claims) if c.system_id == s]].mean(axis=0)
                    for s in unique_systems
                ]
                pairwise = [calculate_cosine_distance(a, b) for a, b in combinations(system_centroids, 2)]
                variance_score = float(np.mean(pairwise)) if pairwise else 0.0

            # 7. Stage Candidate for Human Review
            candidate = InductionCandidate(
                suggested_name=name_suggestion,
                aliases=list({get_claim_text(c)[:50] for c in cluster_claims[:5]}),
                suggested_type=suggested_type,
                suggested_importance=min(1.0, variance_score * 2),
                variance_score=variance_score,
                claim_frequency=len(cluster_claims),
                sample_claims={str(s): next((get_claim_text(c) for c in cluster_claims if c.system_id == s), "") for s in unique_systems[:3]}
            )
            db.add(candidate)
        
        db.commit()
        logger.info(f"Nightly ontology induction complete. Graph candidates staged.")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ontology induction pipeline failed: {e}")
    finally:
        db.close()