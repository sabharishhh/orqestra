"""
Sprint 10 Task 3 — Baseline cleanup for demo-fitness.

Deletes observed claim/contradiction history so the measurement runner
starts from an empty SCCG. Preserves everything the measurement infra
depends on: org, systems, subscriptions, Canon stores, declared
canonical values, presets.

Idempotent — safe to rerun. Prints before/after counts so you can
verify what changed.

Usage:
    docker compose exec api python -m scripts.reset_demo_baseline
    docker compose exec api python -m scripts.reset_demo_baseline --dry-run
    docker compose exec api python -m scripts.reset_demo_baseline --org demo-fitness
"""
import argparse
import logging
import sys
from uuid import UUID

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from core.database import SessionLocal
from models.database import Organization

logging.basicConfig(level=logging.INFO, format="[reset_baseline] %(message)s")
logger = logging.getLogger(__name__)


# Every table we'll TOUCH for demo-fitness — either to count (before/after)
# or to delete. Includes both delete-targets and preserve-targets so the
# script can print a clear before/after diff.
DELETE_TABLES = [
    # order matters: FK-dependent tables first, roots last
    "contradictions",
    "canon_cross_store_conflicts",
    "entity_belief_states",
    "claims",
]

PRESERVE_TABLES = [
    "canonical_entities",
    "canon_stores",
    "system_canon_subscriptions",
    "systems",
    # organizations preserved but not counted (there's exactly one row anyway)
]


def _count(db: Session, table: str, org_id: UUID) -> int:
    """
    Return the row count for a table filtered by org membership.
    Some tables link to org indirectly via joins.
    """
    try:
        if table == "system_canon_subscriptions":
            sql = """
                SELECT COUNT(*) FROM system_canon_subscriptions scs
                JOIN canon_stores cs ON cs.id = scs.store_id
                WHERE cs.org_id = :o
            """
        else:
            sql = f"SELECT COUNT(*) FROM {table} WHERE org_id = :o"
        return db.execute(sql_text(sql), {"o": org_id}).scalar() or 0
    except Exception as e:
        db.rollback()  # release the failed txn so subsequent queries work
        logger.warning(f"  count {table}: {e}")
        return -1



def _delete_one_table(db: Session, table: str, org_id: UUID) -> int:
    """DELETE and return the row count that would have been deleted."""
    r = db.execute(
        sql_text(f"DELETE FROM {table} WHERE org_id = :o"),
        {"o": org_id},
    )
    return r.rowcount


def _snapshot_counts(db: Session, org_id: UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in DELETE_TABLES + PRESERVE_TABLES:
        counts[t] = _count(db, t, org_id)
        # Always rollback between counts so a failing one doesn't poison
        # the transaction for the next.
        db.rollback()
    return counts


def _pretty_row(table: str, before: int, after: int, deletes: bool) -> str:
    delta = after - before
    marker = "DELETED" if deletes else "preserved"
    return f"  {table:32s}  before={before:6d}  after={after:6d}  Δ={delta:+d}  [{marker}]"


def main():
    parser = argparse.ArgumentParser(
        description="Reset demo-fitness's claim/contradiction history for Sprint 10 measurement."
    )
    parser.add_argument("--org", default="demo-fitness",
                        help="Slug of the org to reset (default: demo-fitness).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be deleted without touching the DB.")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug=args.org).first()
        if not org:
            logger.error(f"❌ org '{args.org}' not found")
            sys.exit(1)
        org_id = org.id
        logger.info(f"target org: {args.org} (id={org_id})")

        # BEFORE snapshot
        db.rollback()  # fresh view
        before = _snapshot_counts(db, org_id)

        # Refuse to run if the org has zero systems — indicates a fresh install
        # where there's nothing measurement-relevant to reset. Not an error.
        sys_count = _count(db, "systems", org_id)
        if sys_count == 0:
            logger.warning(f"org '{args.org}' has 0 systems — nothing to reset")
            sys.exit(0)

        if args.dry_run:
            logger.info("=== DRY RUN ===")
            for t in DELETE_TABLES:
                logger.info(f"  would DELETE {before[t]} rows from {t}")
            for t in PRESERVE_TABLES:
                logger.info(f"  would preserve {before[t]} rows in {t}")
            logger.info("(no changes made)")
            return

        # ACTUAL DELETE
        logger.info("--- deleting ---")
        deleted_by_table: dict[str, int] = {}
        for t in DELETE_TABLES:
            n = _delete_one_table(db, t, org_id)
            deleted_by_table[t] = n
            logger.info(f"  DELETE {t}: {n} rows")
        db.commit()

        # AFTER snapshot (fresh session state)
        db.rollback()
        after = _snapshot_counts(db, org_id)

        # Report
        print()
        print("=" * 78)
        print(f"Reset complete for org '{args.org}'")
        print("=" * 78)
        for t in DELETE_TABLES:
            print(_pretty_row(t, before[t], after[t], deletes=True))
        print()
        for t in PRESERVE_TABLES:
            print(_pretty_row(t, before[t], after[t], deletes=False))
        print("=" * 78)

        # Post-condition assertions — belt and suspenders
        problems = []
        for t in DELETE_TABLES:
            if after[t] != 0:
                problems.append(f"  {t}: expected 0 after delete, got {after[t]}")
        for t in PRESERVE_TABLES:
            if after[t] != before[t]:
                problems.append(
                    f"  {t}: expected preserved (before={before[t]}) "
                    f"but got after={after[t]}"
                )
        if problems:
            logger.error("❌ post-reset invariants violated:")
            for p in problems:
                logger.error(p)
            sys.exit(2)

        logger.info(f"✅ demo baseline reset. Total rows deleted: "
                    f"{sum(deleted_by_table.values())}")
    finally:
        db.close()


if __name__ == "__main__":
    main()