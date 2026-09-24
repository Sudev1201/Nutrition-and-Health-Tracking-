import datetime
import uuid

from sqlalchemy import Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class WeightLog(TimestampedBase):
    """One weigh-in, on the user's local date.

    One per day: a second weigh-in the same morning replaces the first rather
    than sitting beside it, since two readings an hour apart are one measurement
    and would count twice in the trend. The newest weigh-in is also the profile's
    weight -- see `app/weight/service.py`.
    """

    __tablename__ = "weight_logs"
    __table_args__ = (UniqueConstraint("user_id", "logged_on", name="uq_weight_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    weight_kg: Mapped[float] = mapped_column(Float)


class CalorieAdjustment(TimestampedBase):
    """A recalibration of the calorie target, in force from `effective_from` on.

    Holds the total offset from the energy formula, not a calorie figure: the
    formula is re-evaluated at the current weight every day, and the offset
    corrects only what the formula misses. Stored rather than derived, because a
    step depends on the goal in force when it was taken, and there is no history
    of goals to replay it against.

    The row in force on a date is the latest whose `effective_from` is on or
    before it, so a past day keeps the target it had. A `reset` row (offset 0)
    marks a goal change: it returns the target to the formula and restarts the
    trend window.
    """

    __tablename__ = "calorie_adjustments"
    __table_args__ = (
        UniqueConstraint("user_id", "effective_from", name="uq_adjustment_user_day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    effective_from: Mapped[datetime.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8))  # step | reset
    offset_kcal: Mapped[float] = mapped_column(Float)
    # The trend a step was read from. Null on a reset, which reads none.
    expected_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
