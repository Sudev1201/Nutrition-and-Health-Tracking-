import datetime
import uuid

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class CycleSettings(TimestampedBase):
    """Whether cycle tracking is on. Off unless the user turns it on.

    Its own table rather than a profile column: a profile save replaces the whole
    questionnaire, and a switch set on the Cycle screen has no business being
    reset by an edit to someone's meal times.
    """

    __tablename__ = "cycle_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_cycle_settings_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CycleLog(TimestampedBase):
    """A day of bleeding, with its flow.

    A logged day is a fact, not a prediction. Only 13% of cycles are 28 days, so
    nothing here projects a phase forward; coaching that depends on "days 1-3"
    counts from these rows.
    """

    __tablename__ = "cycle_logs"
    __table_args__ = (UniqueConstraint("user_id", "logged_on", name="uq_cycle_log_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    flow: Mapped[str] = mapped_column(String(8))  # light | medium | heavy


class CycleSymptom(TimestampedBase):
    """A symptom on a day, logged with or without bleeding -- PMS comes before it."""

    __tablename__ = "cycle_symptoms"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on", "symptom", name="uq_cycle_symptom_user_day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    # cramps | bloating | breast_tenderness | low_mood -- the ones the coaching answers.
    symptom: Mapped[str] = mapped_column(String(24))


class CycleScreening(TimestampedBase):
    """Answers to the heavy-bleeding screening questions, as of one day.

    Any yes produces a clinician referral and never a nutrient change: about one
    in five adolescents with heavy bleeding has an underlying bleeding disorder,
    and a dietary answer would suppress that signal.
    """

    __tablename__ = "cycle_screenings"
    __table_args__ = (UniqueConstraint("user_id", "answered_on", name="uq_screening_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    answered_on: Mapped[datetime.date] = mapped_column(Date)
    soaks_within_two_hours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    longer_than_seven_days: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    large_clots: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flooding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
