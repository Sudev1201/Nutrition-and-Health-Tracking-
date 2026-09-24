"""weight and cycle

Six per-user tables and one column.

`weight_logs` holds one weigh-in per day. `calorie_adjustments` holds the offset
from the energy formula that a recalibration step (or a goal-change reset) put in
force from a date: an offset rather than a calorie figure, so the formula can
follow the current weight without the step counting the same change twice.

`cycle_settings`, `cycle_logs`, `cycle_symptoms` and `cycle_screenings` are the
optional cycle feature. Nothing in the targets path reads them: the iron target
already averages menstrual loss, and calories do not move with cycle phase.

`profiles.menstrual_status` is nullable and needs no backfill. A woman's profile
saved before it existed reads as "not postmenopausal", which is what the targets
assumed until now.

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d8e9f0a1b2c3"
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
        "weight_logs",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        unique=("user_id", "logged_on"),
        constraint="uq_weight_user_day",
    )
    _owned(
        "calorie_adjustments",
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("offset_kcal", sa.Float(), nullable=False),
        sa.Column("expected_kg_per_week", sa.Float(), nullable=True),
        sa.Column("observed_kg_per_week", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        unique=("user_id", "effective_from"),
        constraint="uq_adjustment_user_day",
    )
    _owned(
        "cycle_settings",
        sa.Column("enabled", sa.Boolean(), nullable=False),
        unique=("user_id",),
        constraint="uq_cycle_settings_user",
    )
    _owned(
        "cycle_logs",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("flow", sa.String(length=8), nullable=False),
        unique=("user_id", "logged_on"),
        constraint="uq_cycle_log_user_day",
    )
    _owned(
        "cycle_symptoms",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("symptom", sa.String(length=24), nullable=False),
        unique=("user_id", "logged_on", "symptom"),
        constraint="uq_cycle_symptom_user_day",
    )
    _owned(
        "cycle_screenings",
        sa.Column("answered_on", sa.Date(), nullable=False),
        sa.Column("soaks_within_two_hours", sa.Boolean(), nullable=False),
        sa.Column("longer_than_seven_days", sa.Boolean(), nullable=False),
        sa.Column("large_clots", sa.Boolean(), nullable=False),
        sa.Column("flooding", sa.Boolean(), nullable=False),
        unique=("user_id", "answered_on"),
        constraint="uq_screening_user_day",
    )
    op.add_column("profiles", sa.Column("menstrual_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("profiles", "menstrual_status")
    for name in (
        "cycle_screenings",
        "cycle_symptoms",
        "cycle_logs",
        "cycle_settings",
        "calorie_adjustments",
        "weight_logs",
    ):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
