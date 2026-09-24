import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.profile import (
    AvoidedFood,
    FavouriteIngredient,
    HealthCondition,
    MealSlotTime,
    Medication,
    ObservanceRule,
    Profile,
    UsualIntakeItem,
)
from app.models.user import User
from app.nutrition_core.energy import Body

# Every child table of the profile, so a re-save clears them all.
CHILD_MODELS = (
    HealthCondition,
    Medication,
    MealSlotTime,
    ObservanceRule,
    AvoidedFood,
    FavouriteIngredient,
    UsualIntakeItem,
)


def get_profile(db: Session, user: User) -> Profile | None:
    return db.scalars(select(Profile).where(Profile.user_id == user.id)).one_or_none()


def body_of(profile: Profile) -> Body:
    """The body the energy equations and protein are computed for."""
    return Body(
        sex=profile.sex,
        age=profile.age,
        weight_kg=profile.weight_kg,
        activity=profile.activity,
    )


def get_conditions(db: Session, user: User) -> list[str]:
    return list(
        db.scalars(select(HealthCondition.code).where(HealthCondition.user_id == user.id))
    )


def get_medications(db: Session, user: User) -> list[Medication]:
    return list(db.scalars(select(Medication).where(Medication.user_id == user.id)))


def get_meal_times(db: Session, user: User) -> list[MealSlotTime]:
    return list(
        db.scalars(
            select(MealSlotTime).where(MealSlotTime.user_id == user.id).order_by(MealSlotTime.id)
        )
    )


def get_observances(db: Session, user: User) -> list[ObservanceRule]:
    return list(db.scalars(select(ObservanceRule).where(ObservanceRule.user_id == user.id)))


def get_preferences(db: Session, user: User, model) -> list:
    """The likes or avoid list, in the order the user entered it."""
    return list(
        db.scalars(select(model).where(model.user_id == user.id).order_by(model.position))
    )


def get_usual_intake(db: Session, user: User) -> list[UsualIntakeItem]:
    return list(
        db.scalars(
            select(UsualIntakeItem)
            .where(UsualIntakeItem.user_id == user.id)
            .order_by(UsualIntakeItem.position)
        )
    )


def save_profile(db: Session, user: User, payload) -> Profile:
    """Replace the profile and everything hanging off it.

    Onboarding submits the whole questionnaire at once, so a save is a wholesale
    replacement rather than a merge — otherwise a condition the user unticked
    would linger and keep changing their targets.

    The one exception is a slot's reminder. The Reminders screen sets it and the
    questionnaire never asks, so a payload that leaves it out keeps the slot's
    saved setting, and a slot with none gets the default.
    """
    # Read before the delete below, which leaves no row to read it from. Kept as
    # plain values: the bulk delete takes the session's row objects with it.
    reminders = {row.slot: row.reminder_on for row in get_meal_times(db, user)}

    for model in CHILD_MODELS:
        db.execute(delete(model).where(model.user_id == user.id))

    profile = get_profile(db, user)
    fields = {
        "sex": payload.sex,
        "age": payload.age,
        "weight_kg": payload.weight_kg,
        "activity": payload.activity,
        "goal": payload.goal,
        "pace": payload.pace,
        "diet_type": payload.diet_type,
        "cereal_dominant": payload.cereal_dominant,
        # Only a woman's profile carries one. A profile switched to male must not
        # keep a status that would select a female iron row if switched back.
        "menstrual_status": payload.menstrual_status if payload.sex == "female" else None,
    }

    if profile is None:
        profile = Profile(user_id=user.id, **fields)
        db.add(profile)
    else:
        for name, value in fields.items():
            setattr(profile, name, value)

    db.add_all(
        [HealthCondition(user_id=user.id, code=code) for code in payload.conditions]
    )
    db.add_all(
        [
            Medication(user_id=user.id, name=item.name, taken_at=_as_time(item.time))
            for item in payload.medications
        ]
    )
    db.add_all(
        [
            MealSlotTime(
                user_id=user.id,
                slot=item.slot,
                usual_time=_as_time(item.time),
                weekend_time=_as_time(item.weekend_time) if item.weekend_time else None,
                reminder_on=_reminder_on(item, reminders),
                is_enabled=item.is_enabled,
            )
            for item in payload.meal_times
        ]
    )
    db.add_all(
        [
            ObservanceRule(
                user_id=user.id,
                kind=item.kind,
                weekday=item.weekday,
                start_date=item.start_date,
                end_date=item.end_date,
                label=item.label,
            )
            for item in payload.observances
        ]
    )
    for model, items in (
        (AvoidedFood, payload.avoided),
        (FavouriteIngredient, payload.favourites),
    ):
        db.add_all(
            [
                model(
                    user_id=user.id,
                    label=item.label,
                    food_id=item.food_id,
                    food_kind=item.food_kind,
                    position=index,
                )
                for index, item in enumerate(items)
            ]
        )

    db.add_all(
        [
            UsualIntakeItem(
                user_id=user.id,
                slot=item.slot,
                label=item.label,
                food_id=item.food_id,
                food_kind=item.food_kind,
                grams=item.grams,
                position=index,
            )
            for index, item in enumerate(payload.usual_intake)
        ]
    )

    db.flush()
    return profile


def _reminder_on(item, saved: dict[str, bool]) -> bool:
    """The payload's setting, else the slot's saved one, else a new slot's default."""
    if item.reminder_on is not None:
        return item.reminder_on
    return saved.get(item.slot, _reminder_by_default(item.slot))


def _reminder_by_default(slot: str) -> bool:
    # The spec's own example: the optional mid-morning snack should not nag someone
    # who rarely eats it, so its reminder is opt-in.
    return slot != "snack1"


def _as_time(value: str | datetime.time) -> datetime.time:
    if isinstance(value, datetime.time):
        return value
    hour, minute = value.split(":")[:2]
    return datetime.time(int(hour), int(minute))
