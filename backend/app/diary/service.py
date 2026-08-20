import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foods.measures import format_quantity, measures_for_food, resolve_grams
from app.foods.nutrition import nutrients_for_portion
from app.models.diary import MealLog, MealSlotSkip
from app.models.food import Dish, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from app.models.user import User


class FoodNotFound(LookupError):
    """The dish or ingredient being logged does not exist."""


class UnknownMeasure(ValueError):
    """A measure this food does not offer.

    Refused rather than guessed: silently falling back to a default weight would
    log a portion the user never described.
    """


def resolve_portion(
    db: Session,
    food_id: uuid.UUID,
    food_kind: str,
    measure_name: str | None,
    quantity: float | None,
    grams: float | None,
) -> tuple[float, str, bool]:
    """Work a portion out into (grams, label, is_approximate).

    A household measure is the normal path; an explicit weight is for anyone with
    kitchen scales. One of the two is required — an entry with neither cannot be
    costed.
    """
    if measure_name is not None and quantity is not None:
        match = next(
            (
                measure
                for measure in measures_for_food(db, food_id, food_kind)
                if measure.name == measure_name
            ),
            None,
        )
        if match is None:
            raise UnknownMeasure(f"{food_kind} does not offer the measure {measure_name!r}")

        return (
            resolve_grams(quantity, match.grams),
            f"{format_quantity(quantity)} {match.name}",
            match.is_approximate,
        )

    if grams is not None:
        return grams, f"{grams:g} g", False

    raise UnknownMeasure("a portion needs either a household measure or a weight")


def list_entries(db: Session, user: User, on_date: datetime.date) -> list[MealLog]:
    return list(
        db.scalars(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.logged_on == on_date)
            .order_by(MealLog.created_at)
        )
    )


def _ingredient_nutrients(db: Session, ingredient_id: uuid.UUID, grams: float) -> dict[str, float]:
    rows = db.execute(
        select(IngredientNutrient, Nutrient)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(IngredientNutrient.ingredient_id == ingredient_id)
    ).all()
    return {nutrient.code: row.per_100g * grams / 100.0 for row, nutrient in rows}


def entry_nutrients(db: Session, entry: MealLog) -> dict[str, float]:
    """What one logged entry contributes, in canonical units."""
    if entry.dish_id is not None:
        dish = db.get(Dish, entry.dish_id)
        if dish is None:
            return {}
        return nutrients_for_portion(db, dish, entry.grams)

    if entry.ingredient_id is not None:
        return _ingredient_nutrients(db, entry.ingredient_id, entry.grams)

    return {}


def consumed_on(db: Session, user: User, on_date: datetime.date) -> dict[str, float]:
    """Summed intake for a day. An empty dict means nothing was logged at all —
    which the targets service treats as untracked rather than as a zero-intake
    day, so an unused day never generates a shortfall carry."""
    totals: dict[str, float] = {}
    for entry in list_entries(db, user, on_date):
        for code, amount in entry_nutrients(db, entry).items():
            totals[code] = totals.get(code, 0.0) + amount
    return totals


def add_entry(
    db: Session,
    user: User,
    *,
    on_date: datetime.date,
    slot: str,
    food_id: uuid.UUID,
    food_kind: str,
    portion_label: str,
    measure_name: str | None,
    quantity: float | None,
    grams: float,
    is_estimated: bool,
) -> MealLog:
    if food_kind == "dish":
        if db.get(Dish, food_id) is None:
            raise FoodNotFound(f"no dish {food_id}")
        entry = MealLog(
            user_id=user.id,
            logged_on=on_date,
            slot=slot,
            dish_id=food_id,
            portion_label=portion_label,
            measure_name=measure_name,
            quantity=quantity,
            grams=grams,
            is_estimated=is_estimated,
        )
    else:
        if db.get(Ingredient, food_id) is None:
            raise FoodNotFound(f"no ingredient {food_id}")
        entry = MealLog(
            user_id=user.id,
            logged_on=on_date,
            slot=slot,
            ingredient_id=food_id,
            portion_label=portion_label,
            measure_name=measure_name,
            quantity=quantity,
            grams=grams,
            is_estimated=is_estimated,
        )

    db.add(entry)
    db.flush()
    return entry


def delete_entry(db: Session, user: User, entry_id: uuid.UUID) -> bool:
    entry = db.get(MealLog, entry_id)
    # Scoped to the owner: an id from another user's diary must not be deletable.
    if entry is None or entry.user_id != user.id:
        return False
    db.delete(entry)
    return True


def skipped_on(db: Session, user: User, on_date: datetime.date) -> set[str]:
    """The slots the user said they did not eat, on this date.

    Read from its own table, so `consumed_on` below stays untouched -- an empty
    totals dict still means "nothing logged at all", which is what the targets
    service reads as an untracked day.
    """
    return set(
        db.scalars(
            select(MealSlotSkip.slot).where(
                MealSlotSkip.user_id == user.id, MealSlotSkip.logged_on == on_date
            )
        )
    )


def skip_slot(db: Session, user: User, on_date: datetime.date, slot: str) -> bool:
    """Mark a slot skipped. Returns False when it already was.

    Idempotent rather than an error: the unique constraint would turn a double tap
    on Skip into a 500, and a second tap plainly means the same thing as the first.
    """
    existing = db.scalars(
        select(MealSlotSkip).where(
            MealSlotSkip.user_id == user.id,
            MealSlotSkip.logged_on == on_date,
            MealSlotSkip.slot == slot,
        )
    ).one_or_none()
    if existing is not None:
        return False

    db.add(MealSlotSkip(user_id=user.id, logged_on=on_date, slot=slot))
    return True


def unskip_slot(db: Session, user: User, on_date: datetime.date, slot: str) -> bool:
    """Undo a skip. Returns False when there was nothing to undo."""
    existing = db.scalars(
        select(MealSlotSkip).where(
            MealSlotSkip.user_id == user.id,
            MealSlotSkip.logged_on == on_date,
            MealSlotSkip.slot == slot,
        )
    ).one_or_none()
    if existing is None:
        return False

    db.delete(existing)
    return True


def entry_name(db: Session, entry: MealLog) -> str:
    if entry.dish_id is not None:
        dish = db.get(Dish, entry.dish_id)
        return dish.name if dish else "Unknown dish"
    ingredient = db.get(Ingredient, entry.ingredient_id) if entry.ingredient_id else None
    return ingredient.name if ingredient else "Unknown food"
