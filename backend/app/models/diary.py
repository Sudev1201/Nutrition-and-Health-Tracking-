import datetime
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class MealLog(TimestampedBase):
    """One thing eaten, in one slot, on one day.

    Either a dish or an ingredient — both are reachable from food search, and
    both resolve to per-100g nutrients, so the diary accepts either rather than
    forcing everything through a dish.

    There is deliberately no calories-only quick add. A calorie-only entry would
    look like a logged meal while reading as zero for every vitamin and mineral,
    which would quietly poison the compensation ledger and the weekly report.
    """

    __tablename__ = "meal_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The user's local date, not a timestamp: the day boundary is theirs.
    logged_on: Mapped[datetime.date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(12))

    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # A quantity is two numbers. `measure_name` and `quantity` are what the user
    # chose — "half a bowl" — and `grams` is the absolute the nutrient tables
    # need. Storing only one of them loses something: grams alone is unreadable
    # at the table, and a measure alone cannot be costed.
    measure_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    grams: Mapped[float] = mapped_column(Float)

    # Free text from before the picker existed. New rows compose their label from
    # quantity and measure instead; this keeps old entries readable.
    portion_label: Mapped[str] = mapped_column(String(80))

    # Restaurant and eyeballed portions. The weekly report separates these from
    # measured intake so a week eaten out is not shown with false precision.
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MealSlotSkip(TimestampedBase):
    """A slot the user said they did not eat, on one particular day.

    Deliberately its own table rather than a foodless `meal_logs` row. The diary's
    day totals use an empty dict to mean "nothing logged at all", and the targets
    service relies on that to treat an unused day as untracked rather than as a
    day of eating nothing. A skip row living in `meal_logs` would make that dict
    non-empty and start manufacturing shortfall carries the user never earned.

    A consequence worth stating: a day where every slot is skipped still produces
    no carry. A fast is not a debt to repay -- generating a full day's shortfall
    would push someone to overeat for the two days after it.
    """

    __tablename__ = "meal_slot_skips"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on", "slot", name="uq_skip_user_day_slot"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The user's local date, matching `MealLog.logged_on`.
    logged_on: Mapped[datetime.date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(12))
