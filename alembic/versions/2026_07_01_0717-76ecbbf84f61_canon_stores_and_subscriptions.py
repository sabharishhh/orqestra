"""canon stores and subscriptions

Sprint 8 Task 1:
  - canon_stores: first-class canonical-knowledge stores per org
  - system_canon_subscriptions: ordered subscription list per system
  - canon_cross_store_conflicts: log-only table for Task 5
  - canonical_entities.store_id: FK to canon_stores (NOT NULL after backfill)
  - Uniqueness on canonical_entities moves from (org_id, name) to (store_id, name)
  - Backfill: one 'default' store per org; every canonical_entity moves into
    its org's default; every system auto-subscribes at precedence 0.

Zero behavior change post-migration for existing single-store setups.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '76ecbbf84f61'
down_revision: Union[str, Sequence[str], None] = '5caae7c698ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. canon_stores
    op.create_table(
        'canon_stores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_system_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_system_id'], ['systems.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('org_id', 'name', name='_org_store_name_uc'),
    )
    op.create_index('idx_canon_stores_org', 'canon_stores', ['org_id'])

    # 2. system_canon_subscriptions
    op.create_table(
        'system_canon_subscriptions',
        sa.Column('system_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('precedence_rank', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['system_id'], ['systems.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_id'], ['canon_stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('system_id', 'store_id',
                                name='pk_system_canon_subscriptions'),
    )
    op.create_index('idx_scs_system_precedence',
                    'system_canon_subscriptions', ['system_id', 'precedence_rank'])

    # 3. canon_cross_store_conflicts (log-only for Task 5)
    op.create_table(
        'canon_cross_store_conflicts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('canonical_name', sa.String(length=255), nullable=False),
        sa.Column('store_a_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('store_b_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('value_a', sa.Text(), nullable=True),
        sa.Column('value_b', sa.Text(), nullable=True),
        sa.Column('resolved_by_store_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('triggered_by_system_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_a_id'], ['canon_stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_b_id'], ['canon_stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by_store_id'], ['canon_stores.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['triggered_by_system_id'], ['systems.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_conflict_org_detected',
                    'canon_cross_store_conflicts', ['org_id', 'detected_at'])

    # 4. canonical_entities.store_id — add NULLABLE first
    op.add_column(
        'canonical_entities',
        sa.Column('store_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_canonical_entities_store',
        'canonical_entities', 'canon_stores',
        ['store_id'], ['id'], ondelete='CASCADE',
    )

    # 5. Backfill: create one 'default' store per existing org
    op.execute("""
        INSERT INTO canon_stores (id, org_id, name, description, created_at)
        SELECT gen_random_uuid(), o.id, 'default',
               'Auto-created default canon store (Sprint 8 backfill)',
               CURRENT_TIMESTAMP
        FROM organizations o
        WHERE NOT EXISTS (
            SELECT 1 FROM canon_stores cs
            WHERE cs.org_id = o.id AND cs.name = 'default'
        )
    """)

    # 6. Backfill: move every canonical_entity into its org's default store
    op.execute("""
        UPDATE canonical_entities ce
        SET store_id = cs.id
        FROM canon_stores cs
        WHERE cs.org_id = ce.org_id
          AND cs.name = 'default'
          AND ce.store_id IS NULL
    """)

    # 7. Backfill: auto-subscribe every system to its org's default store at rank 0
    op.execute("""
        INSERT INTO system_canon_subscriptions
            (system_id, store_id, precedence_rank, created_at)
        SELECT s.id, cs.id, 0, CURRENT_TIMESTAMP
        FROM systems s
        JOIN canon_stores cs
          ON cs.org_id = s.org_id AND cs.name = 'default'
        WHERE NOT EXISTS (
            SELECT 1 FROM system_canon_subscriptions scs
            WHERE scs.system_id = s.id AND scs.store_id = cs.id
        )
    """)

    # 8. Lock in store_id NOT NULL
    op.alter_column('canonical_entities', 'store_id', nullable=False)

    # 9. Constraint swap on canonical_entities:
    #    remove UNIQUE(org_id, canonical_name), add UNIQUE(store_id, canonical_name)
    #    The old constraint was auto-named by Postgres.
    op.drop_constraint('canonical_entities_org_id_canonical_name_key',
                       'canonical_entities', type_='unique')
    op.create_unique_constraint('_store_canonical_uc',
                                'canonical_entities', ['store_id', 'canonical_name'])


def downgrade() -> None:
    # Restore old uniqueness
    op.drop_constraint('_store_canonical_uc', 'canonical_entities', type_='unique')
    op.create_unique_constraint('canonical_entities_org_id_canonical_name_key',
                                'canonical_entities', ['org_id', 'canonical_name'])

    # Drop store_id (also drops FK)
    op.drop_constraint('fk_canonical_entities_store',
                       'canonical_entities', type_='foreignkey')
    op.drop_column('canonical_entities', 'store_id')

    # Drop new tables (in reverse dependency order)
    op.drop_index('idx_conflict_org_detected', table_name='canon_cross_store_conflicts')
    op.drop_table('canon_cross_store_conflicts')

    op.drop_index('idx_scs_system_precedence', table_name='system_canon_subscriptions')
    op.drop_table('system_canon_subscriptions')

    op.drop_index('idx_canon_stores_org', table_name='canon_stores')
    op.drop_table('canon_stores')