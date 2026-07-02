"""
Sprint 8 isolation contract smoke test.

Runs the five properties Sprint 8 exists to guarantee against the LIVE
dev DB via HTTP. Not a pytest suite — a runnable smoke check that exits
non-zero if any isolation property regresses. Pattern matches
declare_demo_canon.py: ORM for setup where no HTTP endpoint exists,
HTTP for every actual assertion.

Properties tested:
    1. Unauth reads on canon endpoints    → 401
    2. Cross-org resolve                  → no_declaration (no leak)
    3. Cross-org declare                  → 404 (existence not leaked)
    4. F7.1.A endpoints (contradictions/  → 401 without auth
       graph/roi) require auth
    5. Subscription precedence + conflict → high-precedence wins AND
       cross-store conflict row logged

Setup:
    - Uses demo-fitness as ORG A (assumed already seeded + declared).
    - Creates isolation-test-b as ORG B, seeds it, declares one entity.
    - Creates a second store in demo-fitness for the precedence test,
      subscribes a dedicated test system to both stores.
    - Leaves isolation-test-b in the DB on success (see Task 6 notes).

Usage:
    docker compose exec api python -m scripts.isolation_smoke_test
"""
import hashlib
import logging
import os
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import requests
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import (
    CanonicalEntity,
    CanonStore,
    Organization,
    System,
    SystemCanonSubscription,
)


logging.basicConfig(level=logging.INFO, format="[isolation_smoke] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = os.environ.get("ORQESTRA_API_BASE", "http://localhost:8000")


# =====================================================
# HTTP retry wrapper — handles uvicorn --reload mid-run.
# Every requests.get / requests.post routes through requests.request,
# so patching that one function covers all call sites.
# =====================================================
_original_request = requests.request

def _patched_request(method, url, **kwargs):
    last_exc = None
    for attempt in range(10):
        try:
            return _original_request(method, url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            time.sleep(0.5 * (attempt + 1))
    raise last_exc

requests.request = _patched_request


ORG_A_SLUG = "demo-fitness"
ORG_B_SLUG = "isolation-test-b"
ORG_B_NAME = "Isolation Test Org B"
ORG_B_PRESET = "consumer"

# Entity used for the cross-org test — must exist in the org-B preset.
CROSS_ORG_TEST_ENTITY = "meal_plan"
ORG_B_MEAL_PLAN_VALUE = "org-B secret meal plan — must not leak"

# Entity + values used for the precedence test in ORG A.
PRECEDENCE_ENTITY = "workout_schedule"
LOW_PRECEDENCE_VALUE = "LOW-PRECEDENCE store value"
HIGH_PRECEDENCE_VALUE = "HIGH-PRECEDENCE store value"

TEST_ADMIN_B_NAME = "IsolationTestAdmin_B"
TEST_PRECEDENCE_SYSTEM_NAME = "IsolationTestPrecedence"
SECONDARY_STORE_NAME = "isolation-test-secondary-store"


# =====================================================
# Fixture helpers (ORM setup only — never for assertions)
# =====================================================

@dataclass
class OrgFixture:
    org_id: UUID
    default_store_id: UUID
    admin_token: str        # raw API key for the admin system
    admin_system_id: UUID


def _mint_token() -> tuple[str, str]:
    raw = "oq-" + secrets.token_hex(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _get_or_create_admin(db: Session, org_id: UUID, admin_name: str, default_store_id: UUID) -> tuple[System, str]:
    """
    Idempotent admin creation with hash rotation on every call so THIS
    process can auth as it. Same pattern as declare_demo_canon.
    """
    raw, hashed = _mint_token()
    admin = db.query(System).filter_by(name=admin_name).first()
    if admin:
        admin.api_key_hash = hashed
        admin.org_id = org_id
    else:
        admin = System(
            org_id=org_id,
            name=admin_name,
            provider="internal",
            description="Ephemeral admin for isolation smoke test.",
            api_key_hash=hashed,
        )
        db.add(admin)
    db.flush()

    # Subscribe admin to default store at rank 0.
    exists = (
        db.query(SystemCanonSubscription)
          .filter_by(system_id=admin.id, store_id=default_store_id)
          .first()
    )
    if not exists:
        db.add(SystemCanonSubscription(
            system_id=admin.id,
            store_id=default_store_id,
            precedence_rank=0,
        ))
    db.flush()
    return admin, raw


def _ensure_org_b_seeded_and_declared(db: Session) -> OrgFixture:
    """
    Seeds org B via the seed_org module, creates its admin, declares the
    cross-org test entity. Idempotent.
    """
    from scripts.seed_org import seed as seed_org

    # Seed is safe to call every run (upserts).
    seed_org(name=ORG_B_NAME, slug=ORG_B_SLUG, preset_name=ORG_B_PRESET)

    # Fresh session after seed_org (it manages its own).
    org = db.query(Organization).filter_by(slug=ORG_B_SLUG).first()
    if not org:
        raise RuntimeError(f"seed_org completed but org '{ORG_B_SLUG}' not found")

    store = (
        db.query(CanonStore)
          .filter_by(org_id=org.id, name="default")
          .first()
    )
    if not store:
        raise RuntimeError(f"seed_org completed but no default store for '{ORG_B_SLUG}'")

    admin, token = _get_or_create_admin(db, org.id, TEST_ADMIN_B_NAME, store.id)
    db.commit()

    # Snapshot primitives BEFORE the session possibly closes them
    fx = OrgFixture(
        org_id=org.id,
        default_store_id=store.id,
        admin_token=token,
        admin_system_id=admin.id,
    )

    # Declare the cross-org entity in org B via HTTP (proves auth works too).
    r = requests.post(
        f"{API_BASE}/canon/declare",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "store_id": str(fx.default_store_id),
            "canonical_name": CROSS_ORG_TEST_ENTITY,
            "canonical_value": ORG_B_MEAL_PLAN_VALUE,
            "canonical_claim_text": ORG_B_MEAL_PLAN_VALUE,
            "declared_by": "smoke_test_setup",
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"org-B declare setup failed: {r.status_code} {r.text}")

    return fx


def _prepare_org_a_fixture(db: Session) -> OrgFixture:
    """org-A is demo-fitness — must already be seeded + declared."""
    org = db.query(Organization).filter_by(slug=ORG_A_SLUG).first()
    if not org:
        raise RuntimeError(
            f"Org '{ORG_A_SLUG}' not found. Run seed_org + declare_demo_canon first."
        )
    store = (
        db.query(CanonStore)
          .filter_by(org_id=org.id, name="default")
          .first()
    )
    if not store:
        raise RuntimeError(f"Default store missing for '{ORG_A_SLUG}'")

    admin, token = _get_or_create_admin(db, org.id, "IsolationTestAdmin_A", store.id)
    db.commit()
    return OrgFixture(
        org_id=org.id,
        default_store_id=store.id,
        admin_token=token,
        admin_system_id=admin.id,
    )


def _prepare_precedence_fixture(db: Session, org_a: OrgFixture) -> tuple[UUID, UUID, UUID, str]:
    """
    In org-A, create a SECONDARY store and a dedicated test system
    subscribed to both stores. Returns
    (system_id, high_store_id, low_store_id, system_token).
    """
    # Create/find secondary store
    secondary = (
        db.query(CanonStore)
          .filter_by(org_id=org_a.org_id, name=SECONDARY_STORE_NAME)
          .first()
    )
    if not secondary:
        secondary = CanonStore(
            org_id=org_a.org_id,
            name=SECONDARY_STORE_NAME,
            description="Secondary store for isolation smoke precedence test.",
            owner_system_id=None,
        )
        db.add(secondary)
        db.flush()

    # Ensure PRECEDENCE_ENTITY exists in the SECONDARY store's vocabulary.
    sec_vocab = (
        db.query(CanonicalEntity)
          .filter_by(store_id=secondary.id, canonical_name=PRECEDENCE_ENTITY)
          .first()
    )
    if not sec_vocab:
        template = (
            db.query(CanonicalEntity)
              .filter_by(store_id=org_a.default_store_id, canonical_name=PRECEDENCE_ENTITY)
              .first()
        )
        if not template:
            raise RuntimeError(
                f"'{PRECEDENCE_ENTITY}' not present in org-A default store — "
                "seed_org/declare_demo_canon may not have run."
            )
        sec_vocab = CanonicalEntity(
            org_id=org_a.org_id,
            store_id=secondary.id,
            canonical_name=PRECEDENCE_ENTITY,
            description=template.description,
            category=template.category,
            importance=template.importance,
            severity_tier=template.severity_tier,
            cost_critical_usd=template.cost_critical_usd,
            cost_high_usd=template.cost_high_usd,
            source="isolation-smoke-fixture",
        )
        db.add(sec_vocab)
        db.flush()

    # Create/rotate dedicated precedence test system.
    raw_token, hashed = _mint_token()
    tsys = db.query(System).filter_by(name=TEST_PRECEDENCE_SYSTEM_NAME).first()
    if tsys:
        tsys.api_key_hash = hashed
        tsys.org_id = org_a.org_id
    else:
        tsys = System(
            org_id=org_a.org_id,
            name=TEST_PRECEDENCE_SYSTEM_NAME,
            provider="internal",
            description="Ephemeral system for precedence smoke test.",
            api_key_hash=hashed,
        )
        db.add(tsys)
    db.flush()

    # Reset subscriptions: exactly two, default @ rank 0, secondary @ rank 10.
    db.query(SystemCanonSubscription).filter_by(system_id=tsys.id).delete()
    db.flush()
    db.add(SystemCanonSubscription(
        system_id=tsys.id, store_id=org_a.default_store_id, precedence_rank=0,
    ))
    db.add(SystemCanonSubscription(
        system_id=tsys.id, store_id=secondary.id, precedence_rank=10,
    ))
    db.flush()
    db.commit()

    # Snapshot primitives before releasing the session
    tsys_id = tsys.id
    high_store_id = org_a.default_store_id
    low_store_id = secondary.id

    # Now HTTP-declare the two conflicting values.
    r = requests.post(
        f"{API_BASE}/canon/declare",
        headers={"Authorization": f"Bearer {org_a.admin_token}"},
        json={
            "store_id": str(high_store_id),
            "canonical_name": PRECEDENCE_ENTITY,
            "canonical_value": HIGH_PRECEDENCE_VALUE,
            "canonical_claim_text": HIGH_PRECEDENCE_VALUE,
            "declared_by": "smoke_test_precedence",
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"precedence high declare failed: {r.status_code} {r.text}")

    r = requests.post(
        f"{API_BASE}/canon/declare",
        headers={"Authorization": f"Bearer {org_a.admin_token}"},
        json={
            "store_id": str(low_store_id),
            "canonical_name": PRECEDENCE_ENTITY,
            "canonical_value": LOW_PRECEDENCE_VALUE,
            "canonical_claim_text": LOW_PRECEDENCE_VALUE,
            "declared_by": "smoke_test_precedence",
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"precedence low declare failed: {r.status_code} {r.text}")

    return tsys_id, high_store_id, low_store_id, raw_token


# =====================================================
# The five properties
# =====================================================

def check_1_unauth_canon_reads_401() -> tuple[bool, str]:
    r1 = requests.get(f"{API_BASE}/canon/resolve", params={"entity": "x"}, timeout=10)
    r2 = requests.get(f"{API_BASE}/canon/list", timeout=10)
    if r1.status_code == 401 and r2.status_code == 401:
        return True, "resolve+list both 401 without auth"
    return False, f"resolve={r1.status_code}  list={r2.status_code}  (want 401/401)"


def check_2_cross_org_resolve_no_leak(org_b: OrgFixture) -> tuple[bool, str]:
    """
    A: org-B admin resolves CROSS_ORG_TEST_ENTITY → sees ORG B's value only.
    B: org-B admin resolves an entity org-B didn't declare → no_declaration.
    """
    r = requests.get(
        f"{API_BASE}/canon/resolve",
        headers={"Authorization": f"Bearer {org_b.admin_token}"},
        params={"entity": CROSS_ORG_TEST_ENTITY},
        timeout=10,
    )
    if r.status_code != 200:
        return False, f"resolve HTTP {r.status_code}: {r.text}"
    body = r.json()
    if body.get("canonical_value") != ORG_B_MEAL_PLAN_VALUE:
        return False, (
            f"org-B saw wrong value for '{CROSS_ORG_TEST_ENTITY}': "
            f"got={body.get('canonical_value')!r} expected={ORG_B_MEAL_PLAN_VALUE!r}"
        )

    r = requests.get(
        f"{API_BASE}/canon/resolve",
        headers={"Authorization": f"Bearer {org_b.admin_token}"},
        params={"entity": "workout_routine"},  # declared in org-A, NOT in org-B
        timeout=10,
    )
    if r.status_code != 200:
        return False, f"cross-org no-decl HTTP {r.status_code}: {r.text}"
    body = r.json()
    if body.get("resolution_status") != "no_declaration":
        return False, (
            f"org-B saw org-A's 'workout_routine' — LEAK. "
            f"status={body.get('resolution_status')} value={body.get('canonical_value')!r}"
        )
    return True, "org-B sees only org-B declarations; org-A entities not leaked"


def check_3_cross_org_declare_rejected(
    org_a: OrgFixture, org_b: OrgFixture
) -> tuple[bool, str]:
    """org-B admin tries to declare into org-A's default store → 404."""
    r = requests.post(
        f"{API_BASE}/canon/declare",
        headers={"Authorization": f"Bearer {org_b.admin_token}"},
        json={
            "store_id": str(org_a.default_store_id),  # WRONG ORG'S STORE
            "canonical_name": "meal_plan",
            "canonical_value": "attacker value",
            "declared_by": "attacker",
        },
        timeout=10,
    )
    if r.status_code == 404:
        return True, "cross-org declare rejected with 404 (existence not leaked)"
    return False, f"expected 404, got {r.status_code}: {r.text}"


def check_4_f71a_endpoints_require_auth() -> tuple[bool, str]:
    codes = {
        "contradictions": requests.get(f"{API_BASE}/contradictions/", timeout=10).status_code,
        "graph":          requests.get(f"{API_BASE}/graph/",          timeout=10).status_code,
        "roi":            requests.get(f"{API_BASE}/roi/summary",     timeout=10).status_code,
    }
    if all(c == 401 for c in codes.values()):
        return True, "contradictions+graph+roi all 401 without auth"
    return False, f"codes={codes} (want all 401)"


def check_5_precedence_and_conflict_logging(
    db: Session, test_system_token: str, test_system_id: UUID,
    high_store_id: UUID, low_store_id: UUID,
) -> tuple[bool, str]:
    before = db.execute(sql_text("""
        SELECT COUNT(*) FROM canon_cross_store_conflicts
        WHERE canonical_name = :name AND triggered_by_system_id = :sid
    """), {"name": PRECEDENCE_ENTITY, "sid": test_system_id}).scalar()

    r = requests.get(
        f"{API_BASE}/canon/resolve",
        headers={"Authorization": f"Bearer {test_system_token}"},
        params={"entity": PRECEDENCE_ENTITY},
        timeout=10,
    )
    if r.status_code != 200:
        return False, f"precedence resolve HTTP {r.status_code}: {r.text}"

    body = r.json()
    got = body.get("canonical_value")
    if got != HIGH_PRECEDENCE_VALUE:
        return False, (
            f"precedence lost: got {got!r}, expected {HIGH_PRECEDENCE_VALUE!r}"
        )
    if str(body.get("resolved_from_store_id")) != str(high_store_id):
        return False, (
            f"wrong store won: resolved_from_store_id="
            f"{body.get('resolved_from_store_id')} expected={high_store_id}"
        )
    if not body.get("cross_store_conflict_logged"):
        return False, "conflict not flagged in response body"

    after = db.execute(sql_text("""
        SELECT COUNT(*) FROM canon_cross_store_conflicts
        WHERE canonical_name = :name AND triggered_by_system_id = :sid
    """), {"name": PRECEDENCE_ENTITY, "sid": test_system_id}).scalar()

    if after <= before:
        return False, (
            f"no new row in canon_cross_store_conflicts "
            f"(before={before}, after={after})"
        )

    return True, (
        f"high-precedence value served; conflict row written "
        f"({before} → {after})"
    )


# =====================================================
# Runner
# =====================================================
def main():
    db: Session = SessionLocal()
    failures: list[str] = []
    try:
        logger.info("=" * 60)
        logger.info("Sprint 8 isolation contract smoke test")
        logger.info("=" * 60)

        logger.info("Preparing fixtures…")
        org_a = _prepare_org_a_fixture(db)
        org_b = _ensure_org_b_seeded_and_declared(db)
        (test_system_id, high_store_id, low_store_id,
         test_system_token) = _prepare_precedence_fixture(db, org_a)
        logger.info(f"  org_a.id={org_a.org_id}  org_b.id={org_b.org_id}")
        logger.info(f"  precedence test system id={test_system_id}")

        checks = [
            ("1. unauth canon reads → 401",
             check_1_unauth_canon_reads_401),
            ("2. cross-org resolve no leak",
             lambda: check_2_cross_org_resolve_no_leak(org_b)),
            ("3. cross-org declare rejected (404)",
             lambda: check_3_cross_org_declare_rejected(org_a, org_b)),
            ("4. F7.1.A endpoints require auth",
             check_4_f71a_endpoints_require_auth),
            ("5. subscription precedence + conflict logged",
             lambda: check_5_precedence_and_conflict_logging(
                 db, test_system_token, test_system_id,
                 high_store_id, low_store_id,
             )),
        ]

        for label, fn in checks:
            ok, detail = fn()
            marker = "✓" if ok else "✗"
            logger.info(f"  {marker} {label}: {detail}")
            if not ok:
                failures.append(label)
    finally:
        db.close()

    logger.info("=" * 60)
    if failures:
        logger.error(f"❌ {len(failures)} isolation check(s) FAILED:")
        for f in failures:
            logger.error(f"    - {f}")
        sys.exit(2)
    logger.info("✅ All 5 isolation properties hold.")


if __name__ == "__main__":
    main()