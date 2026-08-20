"""Where the user is starting from.

Onboarding never asks for a calorie figure — most people do not know theirs, and
a guess would be worse than nothing. It asks what a usual day looks like as real
foods, and the baseline is computed from the food database.

This is **not** a target. The target still comes from the ICMR energy formula.
The baseline's job is to show the gap between what the user eats now and what
they need, so the first week's plan is a realistic step rather than a jump.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foods.nutrition import nutrients_for_portion
from app.models.food import Dish, IngredientNutrient
from app.models.nutrient import Nutrient
from app.models.user import User
from app.profiles import service as profiles
from app.targets import service as targets

# Beyond this, the two numbers disagree so badly that the likelier explanation is
# a mistyped weight or a half-described day than a real deficit of that size.
IMPLAUSIBLE_SHARE = 0.4


@dataclass(frozen=True)
class NutrientBaseline:
    """One nutrient's usual-day figure against its published target.

    Self-describing, matching the `targets/today` convention, so a client does
    not need a second lookup to render a row.
    """

    code: str
    display_name: str
    unit: str
    category: str
    kind: str  # target | ceiling
    ear: float | None
    rda: float
    tul: float | None
    usual: float
    # True when a usual day misses the mark, in whichever direction is wrong for
    # this nutrient: short of the figure for a target, over it for a ceiling.
    # Collapsing the two into one `usual - rda` sign would tell someone eating
    # very little salt to eat more of it.
    off_target: bool


@dataclass(frozen=True)
class Baseline:
    has_usual_intake: bool
    usual_energy_kcal: float | None
    target_energy_kcal: float
    difference_kcal: float | None
    implausible: bool
    note: str | None
    nutrients: list[NutrientBaseline]


def nutrients_for_food(
    db: Session, food_id: uuid.UUID, food_kind: str, grams: float
) -> dict[str, float]:
    """What one food at one weight contributes, in canonical units."""
    if food_kind == "dish":
        dish = db.get(Dish, food_id)
        return nutrients_for_portion(db, dish, grams) if dish else {}

    rows = db.execute(
        select(IngredientNutrient, Nutrient)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(IngredientNutrient.ingredient_id == food_id)
    ).all()
    return {nutrient.code: row.per_100g * grams / 100.0 for row, nutrient in rows}


def total_nutrients(db: Session, items: list[tuple[uuid.UUID, str, float]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for food_id, food_kind, grams in items:
        for code, amount in nutrients_for_food(db, food_id, food_kind, grams).items():
            totals[code] = totals.get(code, 0.0) + amount
    return totals


def _off_target(kind: str, usual: float, rda: float) -> bool:
    return usual > rda if kind == "ceiling" else usual < rda


def compute(db: Session, user: User, target_date) -> Baseline | None:
    profile = profiles.get_profile(db, user)
    if profile is None:
        return None

    resolved = targets.resolve_day(db, user, target_date)
    target_energy = next(
        (row.rda for row in resolved.nutrients if row.code == "energy"), 0.0
    ) if resolved else 0.0

    items = profiles.get_usual_intake(db, user)
    if not items:
        # Zero would read as "you eat nothing", which is a very different claim
        # from "you have not told us yet".
        return Baseline(
            has_usual_intake=False,
            usual_energy_kcal=None,
            target_energy_kcal=target_energy,
            difference_kcal=None,
            implausible=False,
            note=None,
            # Empty rather than zeroed, for the same reason
            # `usual_energy_kcal` is null here.
            nutrients=[],
        )

    totals = total_nutrients(
        db, [(item.food_id, item.food_kind, item.grams) for item in items]
    )
    usual = totals.get("energy", 0.0)

    difference = usual - target_energy
    implausible = target_energy > 0 and abs(difference) / target_energy > IMPLAUSIBLE_SHARE

    note = None
    if implausible:
        direction = "less" if difference < 0 else "more"
        note = (
            f"Your usual day works out at about {usual:,.0f} kcal, which is a lot {direction} "
            f"than the {target_energy:,.0f} kcal your profile calls for. That usually means a "
            "meal is missing from the list or a weight is off, rather than a real gap this "
            "size — worth a second look before you start."
        )

    nutrients = [
        NutrientBaseline(
            code=row.code,
            display_name=row.display_name,
            unit=row.unit,
            category=row.category,
            kind=row.kind,
            ear=row.ear,
            rda=row.rda,
            tul=row.tul,
            usual=totals.get(row.code, 0.0),
            off_target=_off_target(row.kind, totals.get(row.code, 0.0), row.rda),
        )
        for row in (resolved.nutrients if resolved else [])
    ]

    return Baseline(
        has_usual_intake=True,
        usual_energy_kcal=usual,
        target_energy_kcal=target_energy,
        difference_kcal=difference,
        implausible=implausible,
        note=note,
        nutrients=nutrients,
    )
