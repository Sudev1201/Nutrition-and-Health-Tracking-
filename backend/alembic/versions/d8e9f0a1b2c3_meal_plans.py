"""meal plans

Two tables. `meal_plans` is one user's Sunday-to-Saturday week, with the seed the
planner was started from so a plan can be reproduced when a suggestion needs
explaining. `meal_plan_items` is one dish per slot per day, carrying both the
household measure and the grams, as the diary does.

One item per slot is a deliberate limit: the unique key on (plan, date, slot) is
what makes swap and lock address a slot unambiguously. The spec's paired snack
beverage would relax it, and needs a beverage tag the seed data does not carry.

Revision ID: d8e9f0a1b2c3
Revises: c75ad3647c6b
Create Date: 2026-09-02

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "c75ad3647c6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "meal_plans",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start", name="uq_plan_user_week"),
    )
    op.create_index(op.f("ix_meal_plans_user_id"), "meal_plans", ["user_id"], unique=False)

    op.create_table(
        "meal_plan_items",
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=12), nullable=False),
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.Column("measure_name", sa.String(length=40), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "plan_date", "slot", name="uq_plan_item_day_slot"),
    )
    op.create_index(
        op.f("ix_meal_plan_items_dish_id"), "meal_plan_items", ["dish_id"], unique=False
    )
    op.create_index(
        op.f("ix_meal_plan_items_plan_date"), "meal_plan_items", ["plan_date"], unique=False
    )
    op.create_index(
        op.f("ix_meal_plan_items_plan_id"), "meal_plan_items", ["plan_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_meal_plan_items_plan_id"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_plan_date"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_dish_id"), table_name="meal_plan_items")
    op.drop_table("meal_plan_items")
    op.drop_index(op.f("ix_meal_plans_user_id"), table_name="meal_plans")
    op.drop_table("meal_plans")
