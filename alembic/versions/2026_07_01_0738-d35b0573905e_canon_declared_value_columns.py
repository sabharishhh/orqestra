"""canon declared value columns

Sprint 8 Task 3 prep:
  canonical_entities gains four columns to hold the human-declared
  canonical value for a (store, name) — the value that reaches agents
  via /canon/resolve. All nullable so existing rows are unaffected;
  a row with canonical_value IS NULL is 'no declaration in this store'.

  - canonical_value:      the actual truth string served to agents
                          (e.g. '180' for max_heart_rate)
  - canonical_claim_text: full sentence form for human display
                          (e.g. 'User max HR is 180 bpm')
  - declared_by:          identifier of the human who declared it
  - declared_at:          when it was declared

  `source` already exists (default 'manual'); Task 2 uses it to
  distinguish 'declared' vs 'promoted' vs 'preset'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd35b0573905e'
down_revision: Union[str, Sequence[str], None] = '76ecbbf84f61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'canonical_entities',
        sa.Column('canonical_value', sa.Text(), nullable=True),
    )
    op.add_column(
        'canonical_entities',
        sa.Column('canonical_claim_text', sa.Text(), nullable=True),
    )
    op.add_column(
        'canonical_entities',
        sa.Column('declared_by', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'canonical_entities',
        sa.Column('declared_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Fast lookup: "does this store have a declared value for this name?"
    op.create_index(
        'idx_canonical_declared',
        'canonical_entities',
        ['store_id', 'canonical_name'],
        postgresql_where=sa.text('canonical_value IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('idx_canonical_declared', table_name='canonical_entities')
    op.drop_column('canonical_entities', 'declared_at')
    op.drop_column('canonical_entities', 'declared_by')
    op.drop_column('canonical_entities', 'canonical_claim_text')
    op.drop_column('canonical_entities', 'canonical_value')