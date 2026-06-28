"""
Canon Read API — the canonical-knowledge query layer.

Agents call this BEFORE responding to a user, to anchor their response on
the org-wide consensus instead of fabricating their own version. Where the
detection pipeline (workers/) is reactive — "you contradicted yourself" —
Canon is proactive — "here's what your org actually believes."

The data path:
    Agent  -->  GET /canon/resolve?entity=X (with Bearer token)
    Bearer token  -->  System  -->  org_id (tenant scope)
    entity hint  -->  entity_resolver.resolve_entity_hint  -->  canonical name
    canonical name  -->  EntityBeliefState rows for this org, this entity
    aggregated centroid  -->  nearest matching Claim's text
    response  -->  { canonical_answer, confidence, consensus_strength, ... }

Read-only by design. The OBG continues to be written by the detection
pipeline; Canon never mutates it. Future sprints can add write-back
(agents propose updates) and enforcement (block deviant outputs).
"""
import logging
from observability import get_logger
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from api.auth import verify_api_key
from core.database import get_db
from models.database import (
    Claim,
    CanonicalEntity,
    EntityBeliefState,
    System,
)
from services.entity_resolver import resolve_entity_hint

logger = get_logger(__name__)
router = APIRouter()


# =====================================================
# Helpers
# =====================================================
def _consensus_strength(confidence: float, system_count: int, sample_count: int) -> str:
    """
    Human-readable label for how settled an org's belief is on this entity.

    Driven by three signals:
      - confidence: Welford-derived score from OBG (0..1)
      - system_count: how many distinct agents have asserted claims on this entity
      - sample_count: total claims observed
    """
    if system_count == 0 or sample_count == 0:
        return "none"
    if confidence < 0.30 or sample_count < 3:
        return "weak"
    if confidence < 0.60 or system_count < 2:
        return "emerging"
    if confidence < 0.85:
        return "strong"
    return "definitive"


def _aggregate_centroid(beliefs: list[EntityBeliefState]) -> np.ndarray:
    """
    Weighted average of per-system centroids by sample_count. Larger
    samples carry proportionally more weight in the org-wide centroid.
    """
    centroids = []
    weights = []
    for b in beliefs:
        if b.centroid_embedding is None or len(b.centroid_embedding) == 0:
            continue
        centroids.append(np.array(b.centroid_embedding))
        weights.append(max(1, b.sample_count))

    if not centroids:
        return None

    centroids_arr = np.vstack(centroids)
    weights_arr = np.array(weights, dtype=float)
    weights_arr /= weights_arr.sum()
    return np.average(centroids_arr, axis=0, weights=weights_arr)


def _nearest_claim_text(
    db: Session,
    org_id: str,
    canonical_name: str,
    target_centroid: np.ndarray,
) -> Optional[dict]:
    """
    Find the Claim in this org whose embedding is closest to the aggregated
    centroid. Returns the claim's S+P+O text and metadata. pgvector handles
    the indexed nearest-neighbor query.
    """
    query = sql_text("""
        SELECT
            c.id,
            c.subject,
            c.predicate,
            c.object,
            c.system_id,
            c.extracted_at,
            (c.embedding <=> CAST(:emb AS vector)) AS distance
        FROM claims c
        WHERE c.org_id = :org_id
          AND c.entity_hint = :entity
          AND c.embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT 1
    """)
    row = db.execute(query, {
        "org_id": org_id,
        "entity": canonical_name,
        "emb": str(target_centroid.tolist()),
    }).first()

    if row is None:
        return None

    return {
        "claim_id": str(row.id),
        "text": f"{row.subject} {row.predicate} {row.object}",
        "source_system_id": str(row.system_id),
        "as_of": row.extracted_at.isoformat() if row.extracted_at else None,
        "centroid_distance": float(row.distance) if row.distance is not None else None,
    }


# =====================================================
# GET /canon/resolve
# =====================================================
@router.get("/resolve")
def resolve_canon(
    entity: str = Query(..., description="Entity hint to resolve. Aliases are accepted."),
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Return the org's canonical answer for an entity.

    Auth resolves the caller's org from their API key — no org_id in the
    query, so a customer can never accidentally (or maliciously) query
    another tenant's beliefs.

    Aliases are accepted: 'weekly_schedule' resolves to 'workout_schedule'
    via the same path the extraction pipeline uses.
    """
    org_id = str(system.org_id)

    # Resolve aliases -> canonical name. Embedding-based fallback omitted
    # here intentionally: callers should pass entity names, not raw text.
    canonical = resolve_entity_hint(org_id=org_id, raw_hint=entity, embedding=None, db=db)

    # Pull all per-system belief states for this org/entity
    beliefs = (
        db.query(EntityBeliefState)
          .filter(
              EntityBeliefState.org_id == org_id,
              EntityBeliefState.entity_name == canonical,
              EntityBeliefState.sample_count >= 1,
          )
          .all()
    )

    if not beliefs:
        # We know about the entity (it canonicalized) but nobody's asserted
        # anything yet. Return a 'no consensus' shape rather than 404.
        return {
            "entity_requested": entity,
            "entity_resolved": canonical,
            "canonical_answer": None,
            "confidence": 0.0,
            "consensus_strength": "none",
            "source_systems": [],
            "sample_count": 0,
            "claim_id": None,
            "as_of": None,
            "note": "No claims observed yet for this entity in your org.",
        }

    # Aggregate per-system centroids into one org-wide centroid
    target_centroid = _aggregate_centroid(beliefs)
    if target_centroid is None:
        raise HTTPException(
            status_code=500,
            detail="OBG centroids unreadable for this entity; OBG corruption suspected.",
        )

    # Find the canonical claim closest to that centroid
    canon_claim = _nearest_claim_text(db, org_id, canonical, target_centroid)
    if canon_claim is None:
        # Beliefs exist but no underlying claim survived — corruption or partial wipe
        raise HTTPException(
            status_code=500,
            detail="OBG entry exists but no matching claim found.",
        )

    # Aggregate confidence: weighted by sample_count, same as centroid
    total_samples = sum(b.sample_count for b in beliefs)
    weighted_conf = sum(
        (b.confidence or 0.0) * b.sample_count for b in beliefs
    ) / max(1, total_samples)

    # System provenance — which agents have touched this entity
    source_system_ids = list({str(b.system_id) for b in beliefs})
    source_systems = (
        db.query(System.id, System.name)
          .filter(System.id.in_(source_system_ids))
          .all()
    )
    source_payload = [
        {"system_id": str(s.id), "system_name": s.name}
        for s in source_systems
    ]

    strength = _consensus_strength(
        confidence=weighted_conf,
        system_count=len(source_system_ids),
        sample_count=total_samples,
    )

    # Newest observation among the belief rows
    last_updated = max(
        (b.last_updated_at for b in beliefs if b.last_updated_at),
        default=None,
    )

    return {
        "entity_requested": entity,
        "entity_resolved": canonical,
        "canonical_answer": canon_claim["text"],
        "confidence": round(weighted_conf, 4),
        "consensus_strength": strength,
        "source_systems": source_payload,
        "sample_count": total_samples,
        "claim_id": canon_claim["claim_id"],
        "as_of": canon_claim["as_of"],
        "last_updated": last_updated.isoformat() if last_updated else None,
    }


# =====================================================
# GET /canon/list
# =====================================================
@router.get("/list")
def list_canon(
    include_empty: bool = Query(False, description="Include canonical entities with zero observations."),
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    List all canonical entities the caller's org has knowledge about.

    Returns the org's registered vocabulary (from canonical_entities) plus
    how much consensus data exists for each. Useful for clients to discover
    what they can ask about.
    """
    org_id = str(system.org_id)

    # Pull the full canonical vocabulary for the org
    entities = (
        db.query(CanonicalEntity)
          .filter(CanonicalEntity.org_id == org_id)
          .order_by(CanonicalEntity.canonical_name)
          .all()
    )

    if not entities:
        return {"org_id": org_id, "entities": []}

    # One aggregated row per entity, joined to OBG totals
    rows = db.execute(sql_text("""
        SELECT
            ce.canonical_name,
            ce.category,
            ce.severity_tier,
            COALESCE(SUM(obg.sample_count), 0) AS total_samples,
            COUNT(DISTINCT obg.system_id)       AS system_count,
            COALESCE(AVG(obg.confidence), 0.0)  AS avg_confidence
        FROM canonical_entities ce
        LEFT JOIN entity_belief_states obg
            ON obg.org_id = ce.org_id
           AND obg.entity_name = ce.canonical_name
        WHERE ce.org_id = :org_id
        GROUP BY ce.canonical_name, ce.category, ce.severity_tier
        ORDER BY ce.canonical_name
    """), {"org_id": org_id}).all()

    payload = []
    for r in rows:
        strength = _consensus_strength(
            confidence=float(r.avg_confidence or 0.0),
            system_count=int(r.system_count or 0),
            sample_count=int(r.total_samples or 0),
        )
        if strength == "none" and not include_empty:
            continue
        payload.append({
            "entity": r.canonical_name,
            "category": r.category,
            "severity_tier": r.severity_tier,
            "consensus_strength": strength,
            "system_count": int(r.system_count or 0),
            "sample_count": int(r.total_samples or 0),
            "confidence": round(float(r.avg_confidence or 0.0), 4),
        })

    return {"org_id": org_id, "entities": payload}