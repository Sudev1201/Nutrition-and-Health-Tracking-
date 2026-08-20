import datetime
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Profile(TimestampedBase):
    """The onboarding answers that drive every computed target.

    Deliberately stores no height: the ICMR-NIN energy equations are
    weight-based, and the spec found the published reference heights could not
    be verified against any primary source.
    """

    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_profile_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    sex: Mapped[str] = mapped_column(String(8))  # male | female
    age: Mapped[int] = mapped_column(Integer)
    weight_kg: Mapped[float] = mapped_column(Float)
    activity: Mapped[str] = mapped_column(String(12))  # sedentary | moderate | heavy

    goal: Mapped[str] = mapped_column(String(12))  # lose | maintain | gain
    pace: Mapped[str | None] = mapped_column(String(12), nullable=True)  # gentle | steady

    diet_type: Mapped[str] = mapped_column(String(20))

    # ICMR sets protein at 1 g/kg rather than 0.83 for a cereal-based diet with
    # low-quality protein. Self-assessed at onboarding; re-derivable later from
    # the actual cereal:legume:milk ratio in the diary.
    cereal_dominant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class HealthCondition(TimestampedBase):
    __tablename__ = "health_conditions"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_condition_user_code"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))


class Medication(TimestampedBase):
    """A medication and the time it is taken.

    The time is not a note. The levothyroxine window is checked against the
    profile's meal times, so a medication without one cannot be reasoned about.
    """

    __tablename__ = "medications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    taken_at: Mapped[datetime.time] = mapped_column(Time)


class MealSlotTime(TimestampedBase):
    """When each of the five slots usually happens.

    Drives reminders, and makes medication windows concrete — knowing breakfast
    is at 08:00 is what lets the 60-minute levothyroxine gap be checked at all.
    """

    __tablename__ = "meal_slot_times"
    __table_args__ = (UniqueConstraint("user_id", "slot", name="uq_meal_time_user_slot"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    slot: Mapped[str] = mapped_column(String(12))  # breakfast | snack1 | lunch | snack2 | dinner
    usual_time: Mapped[datetime.time] = mapped_column(Time)
    # A Sunday breakfast rarely happens at 8am.
    weekend_time: Mapped[datetime.time | None] = mapped_column(Time, nullable=True)
    reminder_on: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Not everyone eats five times. Turning a snack off is a standing preference
    # about the shape of a normal day, which is a different statement from
    # skipping a meal on one particular day -- that is `MealSlotSkip` below.
    #
    # Only the two snacks are ever disabled. A day without lunch is not a
    # four-meal pattern, it is a skipped lunch.
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ObservanceRule(TimestampedBase):
    """A vegetarian observance. One table covers all three shapes the spec needs:
    a recurring weekday, a date range such as Purattasi, or a single festival date.
    """

    __tablename__ = "observance_rules"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # weekday | date_range | single_date
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=Sunday
    start_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    label: Mapped[str] = mapped_column(String(80))


class FoodPreference(TimestampedBase):
    """A food the user likes or avoids.

    `food_id` points at a real dish or ingredient when the item was chosen from
    search, which is what lets the planner act on it rather than string-matching
    a name. It stays nullable so someone can still name something the database
    does not have; the label is always kept so the list reads back as typed.
    """

    __abstract__ = True

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    food_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    food_kind: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # The order the user entered them in. Neither the random-UUID primary key nor
    # `created_at` (transaction time, identical across one save) can carry it.
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AvoidedFood(FoodPreference):
    """A hard block: nothing containing this is ever suggested.

    Covers allergies and anything the user would simply rather not eat — the
    planner treats both the same way, and asking someone to classify their own
    dislike as medical or not serves no purpose.
    """

    __tablename__ = "avoided_foods"


class FavouriteIngredient(FoodPreference):
    __tablename__ = "favourite_ingredients"


class UsualIntakeItem(TimestampedBase):
    """Part of a typical day, used to work out where the user is starting from.

    Most people do not know their current calorie intake, so onboarding never
    asks for it. It describes a usual day as real foods instead, and the baseline
    is computed from the database — which is only possible because these are food
    references with weights rather than free text.

    This is NOT a target. Its job is to show the gap between what the user eats
    now and what they need, so the first week is a step rather than a jump.
    """

    __tablename__ = "usual_intake_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    slot: Mapped[str] = mapped_column(String(12))
    label: Mapped[str] = mapped_column(String(120))
    food_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    food_kind: Mapped[str] = mapped_column(String(12))
    grams: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
