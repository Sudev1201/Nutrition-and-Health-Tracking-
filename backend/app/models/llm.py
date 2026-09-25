import datetime
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class UserSettings(TimestampedBase):
    """A user's own settings that belong to no questionnaire: today, their LLM key.

    Its own table rather than profile columns: a profile save replaces the whole
    questionnaire, and editing a meal time must not forget a key the user paid for.
    It belongs to the user, not the profile, so it must never join
    `profiles.service.CHILD_MODELS` either.

    The six `llm_*` columns are one key, set together and cleared together:
    removing the key nulls them and keeps the row. The key itself is only ever
    here as `llm_key_ciphertext`, a token from `app.llm.crypto` that opens for
    this user alone. `llm_key_hint` is its last four characters, stored so that
    showing which key is saved never needs a decrypt.
    """

    __tablename__ = "user_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_settings_user"),
        # A half-written key -- a ciphertext with no status, a hint with no
        # ciphertext -- would read as saved and then fail on first use.
        CheckConstraint(
            "num_nulls(llm_provider, llm_model, llm_key_ciphertext, llm_key_hint,"
            " llm_key_status, llm_key_set_at) IN (0, 6)",
            name="ck_user_settings_llm_complete",
        ),
        CheckConstraint(
            "llm_key_status IN ('ok', 'rejected', 'unreadable')",
            name="ck_user_settings_llm_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 'anthropic', the one provider today.
    llm_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # One of app.llm.providers.MODELS, checked against the key when it was saved.
    llm_model: Mapped[str | None] = mapped_column(String(40), nullable=True)
    llm_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_key_hint: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # ok | rejected (the provider refused it on use) | unreadable (this server's
    # keyring no longer opens it). Either of the last two asks for the key again.
    llm_key_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # When the key was saved. TimestampedBase has no updated_at, and created_at is
    # when the row first appeared, which a replaced key does not change.
    llm_key_set_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DishPolish(TimestampedBase):
    """The model's description and cooking tip for one dish, as one user paid for them.

    Keyed by user and dish, never by plan item: a swap, a lock, a regenerate or
    next week's plan all reuse it with nothing to invalidate. `brief_hash` is a
    hash of exactly what was sent (the prompt version, the dish name and its
    ingredient names), and a row whose hash no longer matches is ignored when read
    and replaced on the next polish. Per user, because each user pays for their
    own, and it goes with their account.

    Nothing here is a number, and nothing changes the dish: the planner's dish,
    portion and rationale stay exactly as they are, and this text sits beside them.
    """

    __tablename__ = "dish_polish"
    __table_args__ = (UniqueConstraint("user_id", "dish_id", name="uq_dish_polish_user_dish"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex digest of what was sent for this dish; see app.planner.polish.
    brief_hash: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    # None when the model had no tip, or its tip failed the guard.
    cooking_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The model asked for, one of app.llm.providers.MODELS. Under Claude Opus 5's
    # refusal fallback, Anthropic may have answered on another.
    model: Mapped[str] = mapped_column(String(40))
