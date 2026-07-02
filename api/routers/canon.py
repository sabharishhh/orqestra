"""
Canon API — subscription-scoped resolve/list + human declare/promote.

Sprint 8 Task 2/3:
  Reads (agent-facing):
    GET  /resolve   — subscription-precedence walk, declared-only, fail-null.
    GET  /list      — declared (in scope) + candidates (consensus for humans).

  Writes (human declarations only):
    POST /declare              — declare/redeclare a canonical value for
                                 an existing entity in a specific store.
                                 Idempotent UPSERT on canonical_value.
    POST /promote/{candidate_id}
                               — promote an existing candidate row into a
                                 declared value. Same underlying write as
                                 /declare with source='promoted'.

  Enforcement (v4 thesis):
    - Every endpoint requires verify_api_key. No token → 401.
    - Every write validates the target store belongs to the caller's org.
      Cross-org write → 404 (do not leak existence).
    - "Reject unknown": /declare fails if the (store, canonical_name) row
      doesn't exist in the vocabulary. Vocabulary management (presets)
      and value declaration (truth) are distinct concerns.
    - Consensus is never on the agent path. Only human-declared values
      are returned by /resolve.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from api.auth import verify_api_key
from core.database import get_db
from models.database import (
    CanonicalEntity,
    CanonStore,
    System,
    SystemCanonSubscription,
)
from observability import get_logger, timed
from services.entity_resolver import resolve_entity_hint

logger = get_logger(__name__)
router = APIRouter()


# =====================================================
# Helpers
# =====================================================
def _consensus_strength(confidence: float, system_count: int, sample_count: int) -> str:
    """Dashboard-only signal — never on the agent path."""
    if system_count == 0 or sample_count == 0:
        return "none"
    if confidence < 0.30 or sample_count < 3:
        return "weak"
    if confidence < 0.60 or system_count < 2:
        return "emerging"
    if confidence < 0.85:
        return "strong"
    return "definitive"


def _get_subscribed_stores(db: Session, system_id: UUID, org_id: UUID) -> list[tuple[UUID, int, str]]:
    """
    Return [(store_id, precedence_rank, store_name)] for the caller-system,
    ordered by precedence. Joins on canon_stores.org_id as defense-in-depth.
    """
    with timed("db.query", query_name="canon.subscribed_stores") as ctx:
        rows = db.execute(sql_text("""
            SELECT scs.store_id, scs.precedence_rank, cs.name AS store_name
            FROM system_canon_subscriptions scs
            JOIN canon_stores cs ON cs.id = scs.store_id
            WHERE scs.system_id = :system_id
              AND cs.org_id = :org_id
            ORDER BY scs.precedence_rank ASC, scs.store_id ASC
        """), {"system_id": system_id, "org_id": org_id}).all()
        ctx["row_count"] = len(rows)
    return [(r.store_id, r.precedence_rank, r.store_name) for r in rows]


def _assert_store_in_org(db: Session, store_id: UUID, org_id: UUID) -> CanonStore:
    """
    Load a store and confirm it belongs to the caller's org. Returns 404
    on cross-org access — same shape as "store not found" to avoid
    leaking store existence across orgs.
    """
    store = (
        db.query(CanonStore)
          .filter(CanonStore.id == store_id, CanonStore.org_id == org_id)
          .first()
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _log_cross_store_conflict(
    db: Session,
    *,
    org_id: UUID,
    canonical_name: str,
    winning: CanonicalEntity,
    losing: CanonicalEntity,
    triggered_by_system_id: UUID,
) -> None:
    db.execute(sql_text("""
        INSERT INTO canon_cross_store_conflicts
            (org_id, canonical_name, store_a_id, store_b_id,
             value_a, value_b, resolved_by_store_id, triggered_by_system_id)
        VALUES
            (:org_id, :canonical_name, :store_a, :store_b,
             :value_a, :value_b, :resolved_by, :triggered_by)
    """), {
        "org_id": org_id,
        "canonical_name": canonical_name,
        "store_a": winning.store_id,
        "store_b": losing.store_id,
        "value_a": winning.canonical_value,
        "value_b": losing.canonical_value,
        "resolved_by": winning.store_id,
        "triggered_by": triggered_by_system_id,
    })
    db.commit()
    logger.info(
        "canon.cross_store_conflict",
        canonical_name=canonical_name,
        resolved_by_store_id=str(winning.store_id),
        losing_store_id=str(losing.store_id),
    )

def _log_canon_lookup(
    db: Session,
    *,
    org_id: UUID,
    system_id: UUID,
    entity_requested: str,
    entity_resolved: Optional[str],
    resolution_status: str,
    resolved_from_store_id: Optional[UUID],
    resolved_from_store_name: Optional[str],
) -> None:
    """
    Fire-and-forget log of a Canon lookup event. Never raises — a failure
    to log must not break /canon/resolve on the agent path.
    """
    try:
        db.execute(sql_text("""
            INSERT INTO canon_lookup_events
                (org_id, system_id, entity_requested, entity_resolved,
                 resolution_status, resolved_from_store_id, resolved_from_store_name)
            VALUES
                (:org_id, :system_id, :entity_requested, :entity_resolved,
                 :resolution_status, :resolved_from_store_id, :resolved_from_store_name)
        """), {
            "org_id": org_id,
            "system_id": system_id,
            "entity_requested": entity_requested,
            "entity_resolved": entity_resolved,
            "resolution_status": resolution_status,
            "resolved_from_store_id": resolved_from_store_id,
            "resolved_from_store_name": resolved_from_store_name,
        })
        db.commit()
    except Exception as e:
        logger.warning(
            "canon.lookup_log_failed",
            error=str(e),
            system_id=str(system_id),
            entity=entity_requested,
        )
        try:
            db.rollback()
        except Exception:
            pass

# =====================================================
# GET /canon/resolve  (agent-facing)
# =====================================================
@router.get("/resolve")
def resolve_canon(
    entity: str = Query(..., description="Entity hint to resolve. Aliases accepted."),
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Highest-precedence DECLARED value from the caller-system's subscribed
    stores. Returns null (with resolution_status='no_declaration') if
    nothing declared. Never falls back to consensus.

    Every call — hit or miss — writes one row to canon_lookup_events for
    per-agent observability. The log write is fire-and-forget and must
    never break the resolve response (see _log_canon_lookup).
    """
    org_id = system.org_id
    canonical = resolve_entity_hint(org_id=str(org_id), raw_hint=entity, embedding=None, db=db)

    subscribed = _get_subscribed_stores(db, system.id, org_id)
    if not subscribed:
        raise HTTPException(
            status_code=500,
            detail=(
                f"System {system.id} has no canon store subscriptions. "
                "Every system must be subscribed to at least its org's default store."
            ),
        )

    store_ids = [sid for sid, _, _ in subscribed]
    rank_by_store = {sid: rank for sid, rank, _ in subscribed}
    name_by_store = {sid: name for sid, _, name in subscribed}

    with timed("db.query", query_name="canon.declared_matches") as ctx:
        matches = (
            db.query(CanonicalEntity)
              .filter(
                  CanonicalEntity.org_id == org_id,
                  CanonicalEntity.store_id.in_(store_ids),
                  CanonicalEntity.canonical_name == canonical,
                  CanonicalEntity.canonical_value.isnot(None),
              )
              .all()
        )
        ctx["row_count"] = len(matches)

    if not matches:
        _log_canon_lookup(
            db,
            org_id=org_id,
            system_id=system.id,
            entity_requested=entity,
            entity_resolved=canonical,
            resolution_status="no_declaration",
            resolved_from_store_id=None,
            resolved_from_store_name=None,
        )
        return {
            "entity_requested": entity,
            "entity_resolved": canonical,
            "canonical_value": None,
            "canonical_claim_text": None,
            "resolution_status": "no_declaration",
            "resolved_from_store_id": None,
            "declared_by": None,
            "declared_at": None,
            "note": (
                "No subscribed store has a declared canonical value for this entity. "
                "Consensus is never served on the agent path."
            ),
        }

    matches.sort(key=lambda m: (rank_by_store.get(m.store_id, 10**9), str(m.store_id)))
    winner = matches[0]

    conflict_logged = False
    if len(matches) > 1:
        for loser in matches[1:]:
            if loser.canonical_value != winner.canonical_value:
                _log_cross_store_conflict(
                    db,
                    org_id=org_id,
                    canonical_name=canonical,
                    winning=winner,
                    losing=loser,
                    triggered_by_system_id=system.id,
                )
                conflict_logged = True

    _log_canon_lookup(
        db,
        org_id=org_id,
        system_id=system.id,
        entity_requested=entity,
        entity_resolved=canonical,
        resolution_status="declared",
        resolved_from_store_id=winner.store_id,
        resolved_from_store_name=name_by_store.get(winner.store_id),
    )

    return {
        "entity_requested": entity,
        "entity_resolved": canonical,
        "canonical_value": winner.canonical_value,
        "canonical_claim_text": winner.canonical_claim_text,
        "resolution_status": "declared",
        "resolved_from_store_id": str(winner.store_id),
        "resolved_from_store_name": name_by_store.get(winner.store_id),
        "declared_by": winner.declared_by,
        "declared_at": winner.declared_at.isoformat() if winner.declared_at else None,
        "cross_store_conflict_logged": conflict_logged,
    }


# =====================================================
# GET /canon/list  (dashboard-facing)
# =====================================================
@router.get("/list")
def list_canon(
    include_empty: bool = Query(False, description="Include entities with no observations and no declaration."),
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Two sections:
      declared:   authoritative canonical values in scope (subscribed
                  stores), precedence-resolved. Matches what /resolve
                  would return per name.
      candidates: OBG consensus signals per name — dashboard-only.
                  Never served to agents.
    """
    org_id = system.org_id

    # --- DECLARED SECTION ---
    subscribed = _get_subscribed_stores(db, system.id, org_id)
    declared = []
    if subscribed:
        store_ids = [sid for sid, _, _ in subscribed]
        rank_by_store = {sid: rank for sid, rank, _ in subscribed}
        name_by_store = {sid: name for sid, _, name in subscribed}

        with timed("db.query", query_name="canon.list_declared") as ctx:
            rows = (
                db.query(CanonicalEntity)
                  .filter(
                      CanonicalEntity.org_id == org_id,
                      CanonicalEntity.store_id.in_(store_ids),
                      CanonicalEntity.canonical_value.isnot(None),
                  )
                  .all()
            )
            ctx["row_count"] = len(rows)

        by_name: dict[str, CanonicalEntity] = {}
        for r in rows:
            key = r.canonical_name
            if key not in by_name:
                by_name[key] = r
                continue
            incumbent = by_name[key]
            if rank_by_store.get(r.store_id, 10**9) < rank_by_store.get(incumbent.store_id, 10**9):
                by_name[key] = r

        for name in sorted(by_name.keys()):
            row = by_name[name]
            declared.append({
                "canonical_name": name,
                "canonical_value": row.canonical_value,
                "canonical_claim_text": row.canonical_claim_text,
                "category": row.category,
                "severity_tier": row.severity_tier,
                "resolved_from_store_id": str(row.store_id),
                "resolved_from_store_name": name_by_store.get(row.store_id),
                "declared_by": row.declared_by,
                "declared_at": row.declared_at.isoformat() if row.declared_at else None,
            })

    # --- CANDIDATES SECTION ---
    with timed("db.query", query_name="canon.list_candidates") as ctx:
        rows = db.execute(sql_text("""
            SELECT
                ce.canonical_name,
                ce.category,
                ce.severity_tier,
                COALESCE(SUM(obg.sample_count), 0)  AS total_samples,
                COUNT(DISTINCT obg.system_id)       AS system_count,
                COALESCE(AVG(obg.confidence), 0.0)  AS avg_confidence,
                BOOL_OR(ce.canonical_value IS NOT NULL) AS has_declaration_somewhere
            FROM canonical_entities ce
            LEFT JOIN entity_belief_states obg
                ON obg.org_id = ce.org_id
               AND obg.entity_name = ce.canonical_name
            WHERE ce.org_id = :org_id
            GROUP BY ce.canonical_name, ce.category, ce.severity_tier
            ORDER BY ce.canonical_name
        """), {"org_id": org_id}).all()
        ctx["row_count"] = len(rows)

    candidates = []
    for r in rows:
        strength = _consensus_strength(
            confidence=float(r.avg_confidence or 0.0),
            system_count=int(r.system_count or 0),
            sample_count=int(r.total_samples or 0),
        )
        if strength == "none" and not include_empty:
            continue
        candidates.append({
            "canonical_name": r.canonical_name,
            "category": r.category,
            "severity_tier": r.severity_tier,
            "consensus_strength": strength,
            "system_count": int(r.system_count or 0),
            "sample_count": int(r.total_samples or 0),
            "confidence": round(float(r.avg_confidence or 0.0), 4),
            "already_declared_somewhere_in_org": bool(r.has_declaration_somewhere),
            "note": "Consensus signal — for human promotion review only; never served to agents.",
        })

    return {
        "org_id": str(org_id),
        "declared": declared,
        "candidates": candidates,
    }


# =====================================================
# POST /canon/declare  (human write path)
# =====================================================
class DeclareRequest(BaseModel):
    store_id: UUID = Field(..., description="Target canon store within the caller's org.")
    canonical_name: str = Field(..., min_length=1, max_length=255,
                                description="Must already exist in the target store's vocabulary.")
    canonical_value: str = Field(..., min_length=1,
                                 description="The actual truth string served to agents.")
    canonical_claim_text: Optional[str] = Field(
        None, description="Full sentence form for human display."
    )
    declared_by: str = Field(..., min_length=1, max_length=255,
                             description="Identifier of the human declaring this.")


@router.post("/declare")
def declare_canon(
    payload: DeclareRequest,
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Declare (or redeclare) a canonical value for an existing entity in a
    specific store. Idempotent: repeated declares overwrite value/text/
    declared_by/declared_at. The (store, canonical_name) row must
    already exist — vocabulary is managed separately (presets, admin).
    """
    org_id = system.org_id

    # 1. Enforce store belongs to caller's org.
    _assert_store_in_org(db, payload.store_id, org_id)

    # 2. Reject unknown: vocabulary row must pre-exist in the target store.
    entity = (
        db.query(CanonicalEntity)
          .filter(
              CanonicalEntity.org_id == org_id,
              CanonicalEntity.store_id == payload.store_id,
              CanonicalEntity.canonical_name == payload.canonical_name,
          )
          .first()
    )
    if not entity:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Canonical entity '{payload.canonical_name}' does not exist in the "
                f"target store. Vocabulary must be seeded (via preset or admin) "
                f"before its truth can be declared."
            ),
        )

    # 3. UPSERT the declared value.
    entity.canonical_value = payload.canonical_value
    entity.canonical_claim_text = payload.canonical_claim_text
    entity.declared_by = payload.declared_by
    entity.declared_at = datetime.now(timezone.utc)
    entity.source = "declared"
    db.commit()
    db.refresh(entity)

    logger.info(
        "canon.declared",
        org_id=str(org_id),
        store_id=str(payload.store_id),
        canonical_name=payload.canonical_name,
        declared_by=payload.declared_by,
    )

    return {
        "status": "declared",
        "canonical_entity_id": str(entity.id),
        "store_id": str(entity.store_id),
        "canonical_name": entity.canonical_name,
        "canonical_value": entity.canonical_value,
        "canonical_claim_text": entity.canonical_claim_text,
        "declared_by": entity.declared_by,
        "declared_at": entity.declared_at.isoformat(),
        "source": entity.source,
    }


# =====================================================
# POST /canon/promote/{candidate_id}
# =====================================================
class PromoteRequest(BaseModel):
    canonical_value: str = Field(..., min_length=1,
                                 description="Declared value chosen by the human reviewer.")
    canonical_claim_text: Optional[str] = Field(None)
    declared_by: str = Field(..., min_length=1, max_length=255)


@router.post("/promote/{candidate_id}")
def promote_canon(
    candidate_id: UUID,
    payload: PromoteRequest,
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Promote an existing candidate (a CanonicalEntity row surfaced in
    /list.candidates) into a declared value. Same underlying write as
    /declare but records source='promoted' so we know it came from a
    consensus signal rather than a direct declaration.
    """
    org_id = system.org_id

    entity = (
        db.query(CanonicalEntity)
          .filter(
              CanonicalEntity.id == candidate_id,
              CanonicalEntity.org_id == org_id,
          )
          .first()
    )
    if not entity:
        # 404 for cross-org or nonexistent — don't leak existence.
        raise HTTPException(status_code=404, detail="Candidate not found")

    entity.canonical_value = payload.canonical_value
    entity.canonical_claim_text = payload.canonical_claim_text
    entity.declared_by = payload.declared_by
    entity.declared_at = datetime.now(timezone.utc)
    entity.source = "promoted"
    db.commit()
    db.refresh(entity)

    logger.info(
        "canon.promoted",
        org_id=str(org_id),
        store_id=str(entity.store_id),
        canonical_name=entity.canonical_name,
        candidate_id=str(candidate_id),
        declared_by=payload.declared_by,
    )

    return {
        "status": "promoted",
        "canonical_entity_id": str(entity.id),
        "store_id": str(entity.store_id),
        "canonical_name": entity.canonical_name,
        "canonical_value": entity.canonical_value,
        "canonical_claim_text": entity.canonical_claim_text,
        "declared_by": entity.declared_by,
        "declared_at": entity.declared_at.isoformat(),
        "source": entity.source,
    }

@router.get("/lookups/summary")
def canon_lookups_summary(
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Org-scoped Canon lookup activity rollup for the dashboard header.
    Two windows: last hour and last 24h. Also splits last hour by status.
    """
    org_id = system.org_id
    row = db.execute(sql_text("""
        SELECT
            COUNT(*) FILTER (WHERE at > NOW() - INTERVAL '1 hour')   AS last_hour,
            COUNT(*) FILTER (WHERE at > NOW() - INTERVAL '24 hours') AS last_24h,
            COUNT(*) FILTER (
                WHERE at > NOW() - INTERVAL '1 hour'
                  AND resolution_status = 'declared'
            ) AS last_hour_declared,
            COUNT(*) FILTER (
                WHERE at > NOW() - INTERVAL '1 hour'
                  AND resolution_status = 'no_declaration'
            ) AS last_hour_no_declaration
        FROM canon_lookup_events
        WHERE org_id = :org_id
    """), {"org_id": org_id}).first()

    return {
        "last_hour": row.last_hour,
        "last_24h": row.last_24h,
        "last_hour_by_status": {
            "declared": row.last_hour_declared,
            "no_declaration": row.last_hour_no_declaration,
        },
    }

@router.get("/graph")
def canon_graph(
    system: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Graph-shaped view of the org's Canon vocabulary. Dashboard-only.

    Version A (Sprint 12): flat entity list per store with declared /
    candidate / undeclared states. No subscription-topology edges.
    Ledger #15: Version B (topology + cross-store conflict edges)
    ships when a second store exists in the demo.
    """
    org_id = system.org_id

    rows = db.execute(sql_text("""
        SELECT
            cs.id                                 AS store_id,
            cs.name                               AS store_name,
            cs.description                        AS store_description,
            ce.id                                 AS entity_id,
            ce.canonical_name,
            ce.category,
            ce.severity_tier,
            ce.canonical_value,
            ce.canonical_claim_text,
            ce.declared_by,
            ce.declared_at,
            COALESCE(SUM(obg.sample_count), 0)    AS total_samples,
            COUNT(DISTINCT obg.system_id)         AS system_count,
            COALESCE(AVG(obg.confidence), 0.0)    AS avg_confidence
        FROM canon_stores cs
        LEFT JOIN canonical_entities ce
            ON ce.store_id = cs.id
           AND ce.org_id = cs.org_id
        LEFT JOIN entity_belief_states obg
            ON obg.org_id = ce.org_id
           AND obg.entity_name = ce.canonical_name
        WHERE cs.org_id = :org_id
        GROUP BY cs.id, cs.name, cs.description,
                 ce.id, ce.canonical_name, ce.category, ce.severity_tier,
                 ce.canonical_value, ce.canonical_claim_text,
                 ce.declared_by, ce.declared_at
        ORDER BY cs.name, ce.canonical_name
    """), {"org_id": org_id}).all()

    # Group by store
    stores: dict = {}
    for r in rows:
        sid = str(r.store_id)
        if sid not in stores:
            stores[sid] = {
                "store_id": sid,
                "store_name": r.store_name,
                "store_description": r.store_description,
                "entities": [],
            }
        if r.entity_id is None:
            # Store has no entities yet
            continue

        # Determine state
        if r.canonical_value is not None:
            state = "declared"
        elif r.system_count and r.system_count > 0 and r.total_samples > 0:
            state = "candidate"
        else:
            state = "undeclared"

        stores[sid]["entities"].append({
            "entity_id": str(r.entity_id),
            "canonical_name": r.canonical_name,
            "category": r.category,
            "severity_tier": r.severity_tier,
            "state": state,
            "canonical_value": r.canonical_value,
            "canonical_claim_text": r.canonical_claim_text,
            "declared_by": r.declared_by,
            "declared_at": r.declared_at.isoformat() if r.declared_at else None,
            "consensus": {
                "system_count": int(r.system_count or 0),
                "sample_count": int(r.total_samples or 0),
                "confidence": float(r.avg_confidence or 0.0),
                "strength": _consensus_strength(
                    float(r.avg_confidence or 0.0),
                    int(r.system_count or 0),
                    int(r.total_samples or 0),
                ),
            },
        })

    return {
        "org_id": str(org_id),
        "stores": list(stores.values()),
        "summary": {
            "store_count": len(stores),
            "entity_count": sum(len(s["entities"]) for s in stores.values()),
            "declared_count": sum(
                1 for s in stores.values() for e in s["entities"] if e["state"] == "declared"
            ),
            "candidate_count": sum(
                1 for s in stores.values() for e in s["entities"] if e["state"] == "candidate"
            ),
            "undeclared_count": sum(
                1 for s in stores.values() for e in s["entities"] if e["state"] == "undeclared"
            ),
        },
    }