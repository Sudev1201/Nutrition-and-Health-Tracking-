"""meal slot enabling and per-day skips

Two different statements about a meal that did not happen, which the schema keeps
apart on purpose:

`meal_slot_times.is_enabled` is a standing preference about the shape of a normal
day -- someone who eats four times rather than five. It is per user, not per date.

`meal_slot_skips` is one day's fact: no time to eat, or a fast. It is per user per
date per slot, and it lives in its own table rather than as a foodless `meal_logs`
row. The diary's day totals use an empty dict to mean "nothing logged at all", and
the targets service relies on that to treat an unused day as untracked rather than
as a day of eating nothing. A skip inside `meal_logs` would make that dict
non-empty and start manufacturing shortfall carries the user never earned.

Revision ID: c75ad3647c6b
Revises: c1a2b3d4e5f6
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c75ad3647c6b"
down_revision: str | Sequence[str] | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "meal_slot_skips",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=12), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # One skip per slot per day. Without this, a double-tap on the Skip
        # button would leave two rows saying the same thing.
        sa.UniqueConstraint("user_id", "logged_on", "slot", name="uq_skip_user_day_slot"),
    )
    op.create_index(
        op.f("ix_meal_slot_skips_logged_on"), "meal_slot_skips", ["logged_on"], unique=False
    )
    op.create_index(
        op.f("ix_meal_slot_skips_user_id"), "meal_slot_skips", ["user_id"], unique=False
    )

    # `server_default` is required, not cosmetic: the column is NOT NULL and
    # every existing row needs a value. True is the right backfill because every
    # profile saved so far was saved against five slots.
    op.add_column(
        "meal_slot_times",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("meal_slot_times", "is_enabled")
    op.drop_index(op.f("ix_meal_slot_skips_user_id"), table_name="meal_slot_skips")
    op.drop_index(op.f("ix_meal_slot_skips_logged_on"), table_name="meal_slot_skips")
    op.drop_table("meal_slot_skips")
