"""
Systems router.

Sprint 11 revisions:
  - Closes remaining F7.1.A holes: every endpoint now enforces
    verify_api_key + org_id scoping. Cross-org access returns 404
    (existence not leaked).
  - Adds Sprint 11 read endpoints:
      GET /systems/{id}/subscriptions       — canon store subscriptions
      GET /systems/{id}/claims/recent       — recent claims from this system
      GET /systems/{id}/kb                  — KB YAML content (from disk)
"""
from pathlib import Path
from typing import Optional
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from api.auth import verify_api_key
from core.database import get_db
from models.database import CoherenceScore, System

router = APIRouter()


# =====================================================
# Pydantic
# =====================================================
class SystemCreate(BaseModel):
    name: str
    provider: str = "openai"
    description: Optional[str] = None


class SystemResponse(SystemCreate):
    id: UUID


# =====================================================
# Helpers
# =====================================================
def _load_system_scoped(db: Session, system_id: UUID, caller: System) -> System:
    """
    Load a system and confirm it belongs to caller's org. Cross-org access
    returns 404 (not 403) — do not leak the existence of other-org systems.
    """
    sys_ = db.query(System).filter(
        System.id == system_id,
        System.org_id == caller.org_id,
    ).first()
    if not sys_:
        raise HTTPException(status_code=404, detail="System not found")
    return sys_

def _camel_to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)

# =====================================================
# Enriched SystemCreate — backward compatible
# =====================================================
class StoreSubscriptionInput(BaseModel):
    store_id: UUID
    precedence_rank: int = 0


class EnrichedSystemCreate(BaseModel):
    name: str
    provider: str = "openai"
    description: Optional[str] = None
    # New optional fields — Sprint 13.
    kb_yaml: Optional[str] = None
    subscriptions: Optional[list[StoreSubscriptionInput]] = None


class EnrichedSystemResponse(BaseModel):
    id: UUID
    name: str
    provider: str
    description: Optional[str] = None
    # Returned when a KB was provided.
    kb_path: Optional[str] = None
    kb_warnings: list[str] = []
    # Only present on create (never rotated via GET).
    api_token: Optional[str] = None


from pathlib import Path
import hashlib
import re
import secrets

import yaml
from sqlalchemy import text as sql_text

# ... existing imports stay ...


# =====================================================
# Slug helper (matches KB path convention used by /kb endpoint)
# =====================================================
def _camel_to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


# =====================================================
# Enriched SystemCreate — backward compatible
# =====================================================
class StoreSubscriptionInput(BaseModel):
    store_id: UUID
    precedence_rank: int = 0


class EnrichedSystemCreate(BaseModel):
    name: str
    provider: str = "openai"
    description: Optional[str] = None
    # New optional fields — Sprint 13.
    kb_yaml: Optional[str] = None
    subscriptions: Optional[list[StoreSubscriptionInput]] = None


class EnrichedSystemResponse(BaseModel):
    id: UUID
    name: str
    provider: str
    description: Optional[str] = None
    # Returned when a KB was provided.
    kb_path: Optional[str] = None
    kb_warnings: list[str] = []
    # Only present on create (never rotated via GET).
    api_token: Optional[str] = None


# =====================================================
# POST /systems/ — now optionally accepts KB + subscriptions
# =====================================================
@router.post("/", response_model=EnrichedSystemResponse)
async def register_system(
    payload: EnrichedSystemCreate,
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Register a new agent in the caller's org.

    Backward compatible: passing just {name, provider, description} works
    exactly as before. Passing kb_yaml and/or subscriptions authors a
    complete agent: KB file written to disk, subscriptions created,
    fresh API token minted and returned once.

    Post-registration the operator must restart the fleet to activate
    the new container (Ledger #28). The KB file, System row, and token
    persist across restarts.
    """
    # 1. Name uniqueness within org.
    existing = db.query(System).filter(
        System.name == payload.name,
        System.org_id == caller.org_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="System name already registered in this org.")

    # 2. Validate KB YAML shape if provided.
    kb_warnings: list[str] = []
    parsed_kb = None
    if payload.kb_yaml:
        try:
            parsed_kb = yaml.safe_load(payload.kb_yaml)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"KB YAML parse error: {e}")
        if not isinstance(parsed_kb, dict):
            raise HTTPException(status_code=400, detail="KB YAML must parse to a mapping.")
        # Soft-check for expected keys.
        for expected in ("agent_identity", "valid_entities"):
            if expected not in parsed_kb:
                kb_warnings.append(f"KB missing recommended key: {expected}")

    # 3. Validate subscription targets belong to caller's org.
    subs_to_create: list[tuple[UUID, int]] = []
    if payload.subscriptions:
        for sub in payload.subscriptions:
            row = db.execute(sql_text("""
                SELECT id FROM canon_stores
                WHERE id = :sid AND org_id = :org_id
            """), {"sid": sub.store_id, "org_id": caller.org_id}).first()
            if not row:
                raise HTTPException(status_code=404, detail=f"Store {sub.store_id} not found")
            subs_to_create.append((sub.store_id, sub.precedence_rank))
    else:
        # Auto-subscribe to org's default store (fail-closed protection).
        default = db.execute(sql_text("""
            SELECT id FROM canon_stores
            WHERE org_id = :org_id AND name = 'default'
        """), {"org_id": caller.org_id}).first()
        if default:
            subs_to_create.append((default.id, 0))
        else:
            kb_warnings.append("no default store to auto-subscribe; agent must be manually subscribed before use")

    # 4. Cross-reference valid_entities against subscribed stores' vocab.
    if parsed_kb and subs_to_create:
        declared_entities = parsed_kb.get("valid_entities") or []
        store_ids = [sid for sid, _ in subs_to_create]
        vocab_rows = db.execute(sql_text("""
            SELECT DISTINCT canonical_name FROM canonical_entities
            WHERE store_id = ANY(:sids) AND org_id = :org_id
        """), {"sids": store_ids, "org_id": caller.org_id}).all()
        known = {r.canonical_name for r in vocab_rows}
        unknown = [e for e in declared_entities if e not in known]
        if unknown:
            kb_warnings.append(
                f"valid_entities not present in any subscribed store's vocabulary "
                f"(may become promotion candidates later): {unknown}"
            )

    # 5. Mint token.
    raw_token = "oq-" + secrets.token_hex(32)
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()

    # 6. Create the System row.
    new_system = System(
        name=payload.name,
        provider=payload.provider,
        description=payload.description,
        org_id=caller.org_id,
        api_key_hash=hashed,
    )
    db.add(new_system)
    db.flush()  # get new_system.id

    # 7. Create subscription rows.
    for store_id, rank in subs_to_create:
        db.execute(sql_text("""
            INSERT INTO system_canon_subscriptions (system_id, store_id, precedence_rank)
            VALUES (:sid, :store_id, :rank)
        """), {"sid": new_system.id, "store_id": store_id, "rank": rank})

    # 8. Write KB file (after DB flush so we can rollback on filesystem failure).
    kb_path_str: Optional[str] = None
    if payload.kb_yaml:
        slug = _camel_to_snake(payload.name)
        kb_dir = Path("/app/demo/kb")
        kb_dir.mkdir(parents=True, exist_ok=True)
        kb_path = kb_dir / f"{slug}.yaml"
        try:
            kb_path.write_text(payload.kb_yaml)
            kb_path_str = str(kb_path)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"KB file write failed: {e}")

    db.commit()
    db.refresh(new_system)

    return EnrichedSystemResponse(
        id=new_system.id,
        name=new_system.name,
        provider=new_system.provider,
        description=new_system.description,
        kb_path=kb_path_str,
        kb_warnings=kb_warnings,
        api_token=raw_token,
    )


@router.get("/", response_model=list[SystemResponse])
async def list_systems(
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """List agents in the caller's org."""
    return db.query(System).filter(System.org_id == caller.org_id).all()


@router.get("/{system_id}/score")
def get_system_coherence(
    system_id: UUID,
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    _load_system_scoped(db, system_id, caller)  # 404 on cross-org
    score = db.query(CoherenceScore).filter_by(system_id=str(system_id)).first()
    if not score:
        raise HTTPException(404, "No coherence score computed yet.")
    return {
        "system_id": str(score.system_id),
        "score": score.score,
        "active_contradictions": score.active_contradictions,
        "severity_breakdown": {
            "critical": score.critical_count,
            "high": score.high_count,
            "medium": score.medium_count,
            "low": score.low_count,
        },
        "window_days": score.window_days,
        "computed_at": score.computed_at,
    }


@router.get("/estate/score")
def get_estate_coherence(
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Estate-level score, org-scoped."""
    scores = (
        db.query(CoherenceScore)
          .join(System, System.id == CoherenceScore.system_id)
          .filter(System.org_id == caller.org_id)
          .all()
    )
    if not scores:
        return {"estate_score": 1.0, "system_count": 0}
    total_active = sum(s.active_contradictions for s in scores)
    weighted = sum(s.score * (1 + s.active_contradictions) for s in scores)
    weights = sum(1 + s.active_contradictions for s in scores)
    return {
        "estate_score": round(weighted / weights, 4) if weights else 1.0,
        "system_count": len(scores),
        "total_active_contradictions": total_active,
    }


# =====================================================
# NEW — Sprint 11 read endpoints
# =====================================================
@router.get("/{system_id}/subscriptions")
def get_system_subscriptions(
    system_id: UUID,
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Return the canon store subscriptions for a system, in precedence order
    (rank ascending = higher priority first). Includes store name so the
    frontend doesn't need to hydrate UUIDs separately.
    """
    _load_system_scoped(db, system_id, caller)

    rows = db.execute(sql_text("""
        SELECT
            scs.store_id,
            cs.name AS store_name,
            cs.description AS store_description,
            scs.precedence_rank
        FROM system_canon_subscriptions scs
        JOIN canon_stores cs ON cs.id = scs.store_id
        WHERE scs.system_id = :sid
          AND cs.org_id = :org_id
        ORDER BY scs.precedence_rank ASC, cs.name ASC
    """), {"sid": system_id, "org_id": caller.org_id}).all()

    return {
        "system_id": str(system_id),
        "subscriptions": [
            {
                "store_id": str(r.store_id),
                "store_name": r.store_name,
                "store_description": r.store_description,
                "precedence_rank": r.precedence_rank,
            }
            for r in rows
        ],
    }


@router.get("/{system_id}/claims/recent")
def get_system_recent_claims(
    system_id: UUID,
    limit: int = Query(20, ge=1, le=200),
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Return the most recent claims from this system, ordered by extracted_at DESC.
    Includes entity_hint for the frontend's grouping/filtering needs.
    """
    _load_system_scoped(db, system_id, caller)

    rows = db.execute(sql_text("""
        SELECT
            c.id,
            c.subject,
            c.predicate,
            c.object,
            c.entity_hint,
            c.event_type,
            c.extracted_at,
            c.is_historical
        FROM claims c
        WHERE c.system_id = :sid
          AND c.org_id = :org_id
        ORDER BY c.extracted_at DESC NULLS LAST
        LIMIT :lim
    """), {"sid": system_id, "org_id": caller.org_id, "lim": limit}).all()

    return {
        "system_id": str(system_id),
        "count": len(rows),
        "claims": [
            {
                "id": str(r.id),
                "subject": r.subject,
                "predicate": r.predicate,
                "object": r.object,
                "entity_hint": r.entity_hint,
                "event_type": r.event_type,
                "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
                "is_historical": bool(r.is_historical),
            }
            for r in rows
        ],
    }


@router.get("/{system_id}/kb")
def get_system_kb(
    system_id: UUID,
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Return the KB YAML for this system, if one is present on disk.

    KB paths are conventionally at /app/demo/kb/<slug>.yaml where slug is
    derived from the system's name. If the file doesn't exist (real
    non-demo systems have no on-disk KB), returns kb=null and reason.
    """
    sys_ = _load_system_scoped(db, system_id, caller)

    # Demo convention: FitnessAgent → fitness_agent.yaml (CamelCase → snake_case).
    def _camel_to_snake(name: str) -> str:
        out = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0:
                out.append("_")
            out.append(ch.lower())
        return "".join(out)

    slug = _camel_to_snake(sys_.name)
    kb_path = Path(f"/app/demo/kb/{slug}.yaml")

    if not kb_path.exists():
        return {
            "system_id": str(system_id),
            "system_name": sys_.name,
            "kb_available": False,
            "reason": f"no KB file at {kb_path}",
            "kb": None,
        }

    try:
        with open(kb_path) as f:
            raw_text = f.read()
        parsed = yaml.safe_load(raw_text)
    except Exception as e:
        return {
            "system_id": str(system_id),
            "system_name": sys_.name,
            "kb_available": False,
            "reason": f"parse error: {e!s}",
            "kb": None,
        }

    # Return both a structured version and the raw text (frontend may show either).
    return {
        "system_id": str(system_id),
        "system_name": sys_.name,
        "kb_path": str(kb_path),
        "kb_available": True,
        "kb": {
            "agent_identity": parsed.get("agent_identity", "").strip(),
            "org_policy": parsed.get("org_policy", "").strip(),
            "valid_entities": parsed.get("valid_entities", []),
            "data_access": parsed.get("data_access", {}),
            # domain_knowledge and current_assessment_for_user_001 are large
            # (multi-KB); include as raw for now, frontend collapses them.
            "domain_knowledge_keys": list((parsed.get("domain_knowledge") or {}).keys()),
        },
        "raw_yaml": raw_text,
    }

@router.get("/{system_id}/canon_lookups/recent")
def get_system_canon_lookups(
    system_id: UUID,
    limit: int = Query(50, ge=1, le=500),
    caller: System = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Recent Canon lookup events for this system, newest first.
    Also returns a small status histogram over the window returned.
    """
    _load_system_scoped(db, system_id, caller)

    rows = db.execute(sql_text("""
        SELECT
            id,
            entity_requested,
            entity_resolved,
            resolution_status,
            resolved_from_store_id,
            resolved_from_store_name,
            at
        FROM canon_lookup_events
        WHERE system_id = :sid
          AND org_id = :org_id
        ORDER BY at DESC
        LIMIT :lim
    """), {"sid": system_id, "org_id": caller.org_id, "lim": limit}).all()

    histogram: dict[str, int] = {}
    for r in rows:
        histogram[r.resolution_status] = histogram.get(r.resolution_status, 0) + 1

    return {
        "system_id": str(system_id),
        "count": len(rows),
        "status_histogram": histogram,
        "lookups": [
            {
                "id": r.id,
                "entity_requested": r.entity_requested,
                "entity_resolved": r.entity_resolved,
                "resolution_status": r.resolution_status,
                "resolved_from_store_id": str(r.resolved_from_store_id) if r.resolved_from_store_id else None,
                "resolved_from_store_name": r.resolved_from_store_name,
                "at": r.at.isoformat() if r.at else None,
            }
            for r in rows
        ],
    }