"""reports and reminders

Two per-user tables, one column, one index and one data step.

`push_subscriptions` holds one row per browser endpoint, with the keys a push
payload is encrypted to. The endpoint is unique across users, not per user: it
names a device, and a device re-subscribed by another account moves to it.

`reminder_deliveries` is the exactly-once claim on a reminder: one row per user,
local date and slot, inserted before anything is sent. The unique key is what a
restart, an overlapping cron run or a second instance collides with.

`meal_plans.emphasis` holds the nutrients the previous week's report suggested,
as space-separated codes. Its server default is the backfill: every plan stored
so far was generated before there was a report to take an emphasis from.

`ix_meal_logs_user_day` serves the read the ledger walk, the report and the
reminder runner repeat most: one user's entries on one date.

The data step turns the mid-morning snack's reminder off, the spec's own example
of a reminder that should not nag someone who rarely eats that snack.
`reminder_on` has defaulted to true since the column was added and no screen has
ever written it, so no row holds a choice anyone made. The downgrade leaves it
alone: by then a user may have set it on the Reminders screen, and the two
cannot be told apart.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned(name: str, *columns: sa.Column, unique: tuple[str, ...], constraint: str) -> None:
    """A per-user table: the model's columns, then id and created_at, then keys."""
    op.create_table(
        name,
        sa.Column("user_id", sa.UUID(), nullable=False),
        *columns,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(*unique, name=constraint),
    )
    op.create_index(op.f(f"ix_{name}_user_id"), name, ["user_id"], unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    _owned(
        "push_subscriptions",
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        unique=("endpoint",),
        constraint="uq_push_endpoint",
    )
    _owned(
        "reminder_deliveries",
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        unique=("user_id", "local_date", "slot"),
        constraint="uq_delivery_user_day_slot",
    )
    # `server_default` is required, not cosmetic: the column is NOT NULL and every
    # existing plan needs a value. Empty is right, since none had a report behind it.
    op.add_column(
        "meal_plans",
        sa.Column("emphasis", sa.String(length=200), nullable=False, server_default=""),
    )
    op.create_index("ix_meal_logs_user_day", "meal_logs", ["user_id", "logged_on"], unique=False)
    op.execute(sa.text("UPDATE meal_slot_times SET reminder_on = false WHERE slot = 'snack1'"))


def downgrade() -> None:
    """Downgrade schema."""
    # The reminder_on data step is not reversed; the module docstring says why.
    op.drop_index("ix_meal_logs_user_day", table_name="meal_logs")
    op.drop_column("meal_plans", "emphasis")
    for name in ("reminder_deliveries", "push_subscriptions"):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
