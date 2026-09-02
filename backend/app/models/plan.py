import datetime
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class MealPlan(TimestampedBase):
    """One user's plan for one Sunday-to-Saturday week.

    The plan is per user even inside a household: targets, observances and
    medications are all personal, and the cooking view reconciles members' plans
    after the fact rather than the planner producing one shared menu.
    """

    __tablename__ = "meal_plans"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_plan_user_week"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Always a Sunday. The week runs Sunday to Saturday, per the spec.
    week_start: Mapped[datetime.date] = mapped_column(Date)
    # What the planner's random source was started with. Regenerating draws a new
    # one; keeping it means a plan can be reproduced exactly when a suggestion
    # needs explaining.
    seed: Mapped[int] = mapped_column(Integer)


class MealPlanItem(TimestampedBase):
    """One dish in one slot on one day of a plan.

    A quantity is two numbers here as it is in the diary: the household measure
    the user reads ("3 idli") and the grams the engine costed. Locked items
    survive regeneration and re-planning; everything else is disposable.
    """

    __tablename__ = "meal_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "plan_date", "slot", name="uq_plan_item_day_slot"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), index=True
    )
    plan_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(12))

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), index=True
    )
    grams: Mapped[float] = mapped_column(Float)
    measure_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)

    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Why the planner chose this, in the user's terms. Null when it had nothing
    # worth saying -- an empty reason is worse than none.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
