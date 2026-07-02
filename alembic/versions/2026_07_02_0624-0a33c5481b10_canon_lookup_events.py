"""canon_lookup_events

Revision ID: <auto>
Revises: d35b0573905e
Create Date: <auto>

Sprint 11 Task 2b: persist Canon lookup events.

Every call to /canon/resolve writes one row. Powers:
  - GET /systems/{id}/canon_lookups/recent (per-agent stream)
  - "Canon lookups / hour" tile on EstateScoreHeader
  - Later: per-agent Canon dependency scoring

Insert is best-effort and never blocks resolution — see canon.py.
"""
from alembic import op
import sqlalchemy as sa


revision = "<auto>"  # leave what alembic put here
down_revision = "d35b0573905e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE canon_lookup_events (
            id                       BIGSERIAL PRIMARY KEY,
            org_id                   UUID NOT NULL,
            system_id                UUID NOT NULL,
            entity_requested         TEXT NOT NULL,
            entity_resolved          TEXT,
            resolution_status        TEXT NOT NULL,
            resolved_from_store_id   UUID,
            resolved_from_store_name TEXT,
            at                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX ix_canon_lookup_events_system_at
        ON canon_lookup_events (system_id, at DESC);
    """)
    op.execute("""
        CREATE INDEX ix_canon_lookup_events_org_at
        ON canon_lookup_events (org_id, at DESC);
    """)
    op.execute("""
        CREATE INDEX ix_canon_lookup_events_status
        ON canon_lookup_events (resolution_status);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_canon_lookup_events_status;")
    op.execute("DROP INDEX IF EXISTS ix_canon_lookup_events_org_at;")
    op.execute("DROP INDEX IF EXISTS ix_canon_lookup_events_system_at;")
    op.execute("DROP TABLE IF EXISTS canon_lookup_events;")