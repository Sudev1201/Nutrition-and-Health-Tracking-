"""diary household measures

Splits a diary quantity into the household measure the user chose and the
absolute weight the nutrient tables need, instead of one free-text label.

Revision ID: c1a2b3d4e5f6
Revises: b5fee6701227
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | Sequence[str] | None = "b5fee6701227"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable because rows logged before the picker existed have only the free
    # text, and backfilling a measure onto them would be inventing data.
    op.add_column("meal_logs", sa.Column("measure_name", sa.String(length=40), nullable=True))
    op.add_column("meal_logs", sa.Column("quantity", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("meal_logs", "quantity")
    op.drop_column("meal_logs", "measure_name")
