"""widen ingredient_nutrients source column

Revision ID: 4ea34d5265c2
Revises: 648af976d707
Create Date: 2026-08-16 20:31:04.729236

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4ea34d5265c2'
down_revision: str | Sequence[str] | None = '648af976d707'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    16 chars fit "IFCT" / "USDA" but not the "derived:plant-b12-zero" tag
    the corrected USDA gap-fill loader writes for plant foods
    (see etl/load_usda.py).
    """
    op.alter_column(
        'ingredient_nutrients',
        'source',
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'ingredient_nutrients',
        'source',
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
