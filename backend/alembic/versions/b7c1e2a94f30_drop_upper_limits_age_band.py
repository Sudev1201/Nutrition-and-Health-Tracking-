"""drop upper_limits age_band

Revision ID: b7c1e2a94f30
Revises: 4ea34d5265c2
Create Date: 2026-08-17 10:12:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c1e2a94f30'
down_revision: str | Sequence[str] | None = '4ea34d5265c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    `upper_limits.age_band` defaulted to the string "adult" while
    `rda_reference.age_band` holds "18-59" / "60+". Same column name, two
    vocabularies that never meet: plan 3 resolving a 60+ user finds an RDA and
    zero upper limits on what looks like the same key.

    The upper limits genuinely have no age dimension -- ICMR-NIN and the IOM
    publish one adult TUL per nutrient, with no elderly split -- so this
    encodes that as the absence of a column rather than as a colliding string.
    Unified now, while all 16 rows still say "adult" and the change is free.
    """
    op.drop_constraint('uq_ul_lookup', 'upper_limits', type_='unique')
    op.drop_column('upper_limits', 'age_band')
    op.create_unique_constraint('uq_ul_lookup', 'upper_limits', ['nutrient_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_ul_lookup', 'upper_limits', type_='unique')
    op.add_column(
        'upper_limits',
        sa.Column('age_band', sa.String(length=16), nullable=False, server_default='adult'),
    )
    op.alter_column('upper_limits', 'age_band', server_default=None)
    op.create_unique_constraint('uq_ul_lookup', 'upper_limits', ['nutrient_id', 'age_band'])
