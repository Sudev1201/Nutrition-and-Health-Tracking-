"""Household measures and the absolute weight behind them.

Every quantity in this app is two numbers: the household measure a person
actually thinks in — half a bowl, one glass — and the absolute weight the
nutrient tables are expressed in. One without the other is unusable: "180 g of
sambar" means nothing at the table, and "half a bowl" means nothing to the
science.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import PortionMeasure

# Vessels you drink from. Their absolute reads in ml rather than g — a glass of
# buttermilk is 250 ml to anyone who has ever poured one.
#
# The stored value stays grams, because that is the unit the nutrient tables use.
# For water-based drinks the two are within a couple of percent (milk is 1.03
# g/ml), which is far inside the error of eyeballing a glass in the first place.
DRINKING_VESSELS = frozenset({"glass", "tall glass", "tumbler", "small glass"})

# INDB bakes the count into its serving unit ("1 cup"), which would otherwise
# produce "2 × 1 cup" in the picker.
_LEADING_COUNTS = ("1 ", "one ")


@dataclass(frozen=True)
class Measure:
    name: str
    grams: float
    is_default: bool = False
    # True when the weight is a general figure rather than one measured for this
    # particular food. Entries logged with one are marked estimated.
    is_approximate: bool = False

    @property
    def unit(self) -> str:
        return "ml" if self.name in DRINKING_VESSELS else "g"


"""
Offered when a food carries no measure of its own — which is every one of the
547 ingredients, since only dishes were seeded with them.

Deliberately approximate: a cup of raw rice is about 185 g and a cup of chopped
greens about 30 g, so a single figure cannot be right for both. Flagging them is
what keeps that honest, rather than quietly inventing a weight.
"""
GENERIC_MEASURES: tuple[Measure, ...] = (
    Measure(name="cup", grams=240.0, is_approximate=True),
    Measure(name="glass", grams=250.0, is_approximate=True),
    Measure(name="bowl", grams=200.0, is_approximate=True),
    Measure(name="tablespoon", grams=15.0, is_approximate=True),
    Measure(name="teaspoon", grams=5.0, is_approximate=True),
)


def normalise_measure_name(raw: str) -> str:
    name = raw.strip().lower()
    for prefix in _LEADING_COUNTS:
        name = name.removeprefix(prefix)
    return name.strip()


def format_quantity(quantity: float) -> str:
    """Render a quantity the way people say it: ½ bowl, not 0.5 bowl."""
    fractions = {0.25: "¼", 0.5: "½", 0.75: "¾", 0.33: "⅓", 0.67: "⅔"}

    whole = int(quantity)
    remainder = round(quantity - whole, 2)

    if remainder == 0:
        return str(whole)

    symbol = fractions.get(remainder)
    if symbol is None:
        return f"{quantity:g}"
    return f"{whole}{symbol}" if whole else symbol


def resolve_grams(quantity: float, measure_grams: float) -> float:
    return quantity * measure_grams


def measures_for_food(db: Session, food_id: uuid.UUID, food_kind: str) -> list[Measure]:
    """The measures offered for one food: its own first, then the generic set.

    The generic ones are always appended rather than used only as a fallback, so
    someone can say "half a cup" of a dish whose seeded measure is a plate.
    """
    column = PortionMeasure.dish_id if food_kind == "dish" else PortionMeasure.ingredient_id
    rows = db.scalars(select(PortionMeasure).where(column == food_id)).all()

    own = [
        Measure(
            name=normalise_measure_name(row.measure_name),
            grams=row.grams,
            is_default=row.is_default,
            is_approximate=False,
        )
        for row in rows
    ]

    seen = {measure.name for measure in own}
    generic = [measure for measure in GENERIC_MEASURES if measure.name not in seen]

    return own + generic
