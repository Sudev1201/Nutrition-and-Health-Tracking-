"""ai descriptions

Two per-user tables.

`user_settings` holds one row per user, outside the profile: a profile save
replaces the questionnaire's tables wholesale, and a saved API key must survive
an edit to someone's meal times. Its six `llm_*` columns are one key, set or
cleared together, which `ck_user_settings_llm_complete` enforces;
`ck_user_settings_llm_status` limits the status to ok, rejected and unreadable.
The key is stored only as ciphertext that opens for its own user.

`dish_polish` caches the model's description and cooking tip per user and dish,
keyed by a hash of exactly what was sent. It is keyed to the dish rather than to
plan items, so a swap, a lock, a regenerate or the next week's plan reuse it
with nothing to invalidate. It goes with its user and with its dish.

Both tables start empty, so there is nothing to backfill.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned(
    name: str, *items: sa.Column | sa.Constraint, unique: tuple[str, ...], constraint: str
) -> None:
    """A per-user table: the model's columns and constraints, then id and created_at,
    then keys."""
    op.create_table(
        name,
        sa.Column("user_id", sa.UUID(), nullable=False),
        *items,
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
        "user_settings",
        sa.Column("llm_provider", sa.String(length=16), nullable=True),
        sa.Column("llm_model", sa.String(length=40), nullable=True),
        sa.Column("llm_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("llm_key_hint", sa.String(length=4), nullable=True),
        sa.Column("llm_key_status", sa.String(length=12), nullable=True),
        sa.Column("llm_key_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "num_nulls(llm_provider, llm_model, llm_key_ciphertext, llm_key_hint,"
            " llm_key_status, llm_key_set_at) IN (0, 6)",
            name="ck_user_settings_llm_complete",
        ),
        sa.CheckConstraint(
            "llm_key_status IN ('ok', 'rejected', 'unreadable')",
            name="ck_user_settings_llm_status",
        ),
        unique=("user_id",),
        constraint="uq_user_settings_user",
    )
    _owned(
        "dish_polish",
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("brief_hash", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cooking_note", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="CASCADE"),
        unique=("user_id", "dish_id"),
        constraint="uq_dish_polish_user_dish",
    )
    op.create_index(op.f("ix_dish_polish_dish_id"), "dish_polish", ["dish_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_dish_polish_dish_id"), table_name="dish_polish")
    for name in ("dish_polish", "user_settings"):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
