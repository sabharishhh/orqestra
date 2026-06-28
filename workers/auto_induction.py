import os
import json
import logging
from observability import get_logger
import numpy as np
from datetime import datetime, timedelta, timezone
from itertools import combinations

from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.celery_app import celery_app
from models.database import Claim, InductionCandidate, CanonicalEntity, Organization
from services.config_loader import get_org_config
from openai import OpenAI

logger = get_logger(__name__)


# =====================================================
# MATH UTILS
# =====================================================
def calculate_cosine_distance(emb1, emb2):
    """Safely calculates cosine distance between two raw vector arrays."""
    if emb1 is None or emb2 is None or len(emb1) == 0 or len(emb2) == 0:
        return 1.0
    a, b = np.array(emb1), np.array(emb2)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 1.0
    return float(1.0 - (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))


def get_claim_text(claim: Claim) -> str:
    """Reconstruct text since claim_text isn't a direct column."""
    return f"{claim.subject} {claim.predicate} {claim.object}"


# =====================================================
# LLM canonical naming
# =====================================================
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
        temperature=0.0,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith('```json'):
        raw = raw[7:-3]
    elif raw.startswith('```'):
        raw = raw[3:-3]
    return json.loads(raw.strip())


# =====================================================
# CORE PIPELINE
# =====================================================
def _induce_for_org(db: Session, org_id: str) -> int:
    """
    Run agglomerative clustering + candidate staging for a single org.
    Returns the number of candidates staged.
    """
    cfg = get_org_config(org_id, db)
    lookback_days       = cfg.induction_lookback_days
    cluster_distance    = cfg.induction_cluster_threshold
    min_cluster_size    = cfg.induction_min_cluster_size
    merge_distance      = cfg.induction_merge_threshold

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # 1. Fetch orphaned claims for this org in the lookback window.
    #    "Orphan" = the entity_resolver couldn't map raw_hint to a canonical
    #    entity, so entity_hint is set to the normalized raw string but it's
    #    not in canonical_entities for this org.
    canonical_names = {
        row.canonical_name for row in
        db.query(CanonicalEntity.canonical_name).filter_by(org_id=org_id).all()
    }

    unassigned = (
        db.query(Claim)
          .filter(
              Claim.org_id == org_id,
              Claim.extracted_at >= cutoff,
          )
          .all()
    )
    unassigned = [c for c in unassigned if c.entity_hint not in canonical_names]

    if len(unassigned) < min_cluster_size:
        logger.info(
            f"[{org_id}] Induction: {len(unassigned)} orphan claims, below min_cluster_size={min_cluster_size}. Skipping."
        )
        return 0

    embeddings = np.array([
        c.embedding for c in unassigned
        if c.embedding is not None and len(c.embedding) > 0
    ])
    if len(embeddings) < min_cluster_size:
        return 0

    # 2. Primary clustering pass
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=cluster_distance,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(embeddings)

    clusters = {}
    for claim, label in zip(unassigned, labels):
        clusters.setdefault(label, []).append(claim)

    processed_centroids = []
    staged = 0

    for cluster_id, cluster_claims in clusters.items():
        if len(cluster_claims) < min_cluster_size:
            continue

        cluster_embeddings = np.array([c.embedding for c in cluster_claims])
        centroid = cluster_embeddings.mean(axis=0)

        # 3. F6.1 Mitigation: second-pass merge for overlapping clusters
        is_duplicate = False
        for pc in processed_centroids:
            if calculate_cosine_distance(centroid, pc) < merge_distance:
                is_duplicate = True
                break
        if is_duplicate:
            continue

        processed_centroids.append(centroid)

        # 4. Representative claim = furthest from centroid (most informative example)
        distances = [calculate_cosine_distance(e, centroid) for e in cluster_embeddings]
        representative = cluster_claims[np.argmax(distances)]

        # 5. LLM canonical naming
        try:
            suggestion = llm_suggest_entity_name(
                get_claim_text(representative),
                [get_claim_text(c) for c in cluster_claims[:5]],
            )
            name_suggestion = suggestion.get("name", "unknown_entity")
            suggested_type = suggestion.get("type", "general")
        except Exception as e:
            logger.error(f"[{org_id}] Failed to generate entity name: {e}")
            continue

        # Prevent collisions with existing canonical entities in this org
        existing = (
            db.query(CanonicalEntity)
              .filter_by(org_id=org_id, canonical_name=name_suggestion)
              .first()
        )
        if existing:
            logger.info(
                f"[{org_id}] Induction: candidate '{name_suggestion}' already exists in canonical_entities. Skipping."
            )
            continue

        # 6. Organizational variance score
        unique_systems = list({c.system_id for c in cluster_claims})
        variance_score = 0.0
        if len(unique_systems) > 1:
            system_centroids = [
                cluster_embeddings[[i for i, c in enumerate(cluster_claims) if c.system_id == s]].mean(axis=0)
                for s in unique_systems
            ]
            pairwise = [calculate_cosine_distance(a, b) for a, b in combinations(system_centroids, 2)]
            variance_score = float(np.mean(pairwise)) if pairwise else 0.0

        # 7. Stage candidate for human review (org-scoped)
        candidate = InductionCandidate(
            org_id=org_id,
            suggested_name=name_suggestion,
            aliases=list({get_claim_text(c)[:50] for c in cluster_claims[:5]}),
            suggested_type=suggested_type,
            suggested_importance=min(1.0, variance_score * 2),
            variance_score=variance_score,
            claim_frequency=len(cluster_claims),
            sample_claims={
                str(s): next(
                    (get_claim_text(c) for c in cluster_claims if c.system_id == s),
                    "",
                )
                for s in unique_systems[:3]
            },
        )
        db.add(candidate)
        staged += 1

    return staged


@celery_app.task(queue="claim_extraction")
def run_nightly_induction():
    """
    Worker 5: Unsupervised ontology expansion via Agglomerative Clustering.

    Sprint 3.6b: per-org, with tuning params from DetectionConfig:
      - induction_lookback_days
      - induction_cluster_distance
      - induction_min_cluster_size
      - induction_merge_distance
    """
    db: Session = SessionLocal()
    try:
        org_ids = [str(row.id) for row in db.query(Organization.id).all()]
        if not org_ids:
            logger.info("Induction: no organizations seeded. Nothing to induce.")
            return

        total_staged = 0
        for org_id in org_ids:
            try:
                staged = _induce_for_org(db, org_id)
                total_staged += staged
                if staged > 0:
                    logger.info(f"[{org_id}] Induction: staged {staged} new candidate(s).")
            except Exception as e:
                # One org failing shouldn't kill the rest
                db.rollback()
                logger.error(f"[{org_id}] Induction failed for this org: {e}")
                continue

        db.commit()
        logger.info(f"Nightly ontology induction complete. Total candidates staged: {total_staged}.")

    except Exception as e:
        db.rollback()
        logger.error(f"Ontology induction pipeline failed: {e}")
    finally:
        db.close()# bind-mount test marker
# bind-mount test marker
