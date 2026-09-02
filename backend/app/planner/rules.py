"""Hard constraints on what the planner may suggest.

Pure functions over plain data: no database, no HTTP. The service layer turns
profile rows into these inputs, and the engine never scores a dish this module
has refused -- which is what makes "constraint, not preference" true in code.
"""

import datetime
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

# IFCT's diet vocabulary is cumulative: a fishetarian eats egg, an eggetarian
# does not eat fish. Ranking it turns "may this person eat this dish" into one
# comparison. The profile spells the last one with a hyphen; the dish tag does not.
DISH_DIET_RANK = {
    "vegetarian": 0,
    "eggetarian": 1,
    "fishetarian": 2,
    "nonveg": 3,
}
PROFILE_DIET_RANK = {
    "vegetarian": 0,
    "eggetarian": 1,
    "fishetarian": 2,
    "non-vegetarian": 3,
}

# Guideline research in the spec: the first food or drink of the day at least
# 60 minutes after a levothyroxine-class dose, and calcium- or iron-rich food
# at least four hours clear of it.
EMPTY_STOMACH_MINUTES = 60
MINERAL_CLEARANCE_MINUTES = 240
MINERAL_WINDOW_NUTRIENTS = ("calcium", "iron")
# One default portion carrying this share of the day's requirement makes a dish
# "heavy". The guideline names curd, ragi and milk, which all clear a tenth
# comfortably; plain rice and most tiffin do not. An engineering line, stated
# once, rather than a per-food list that would need maintaining.
MINERAL_HEAVY_SHARE = 0.10


@dataclass(frozen=True)
class Portion:
    grams: float
    measure_name: str | None
    quantity: float | None
    # "3 idli", "1½ cup", or "150 g" when the dish has no seeded measure.
    label: str


@dataclass(frozen=True)
class Candidate:
    """A dish as the planner sees it: what it is, when it fits, what it carries."""

    dish_id: uuid.UUID
    name: str
    slots: frozenset[str]
    diet: str  # vegetarian | eggetarian | fishetarian | nonveg
    ingredient_ids: frozenset[uuid.UUID]
    ingredient_names: tuple[str, ...]
    per_100g: dict[str, float]
    portions: tuple[Portion, ...]  # ascending by grams
    default_grams: float


@dataclass(frozen=True)
class FoodRef:
    """An avoided or favourite food: a real row when picked from search, free text otherwise."""

    label: str
    food_id: uuid.UUID | None = None
    food_kind: str | None = None  # dish | ingredient


@dataclass(frozen=True)
class Observance:
    kind: str  # weekday | date_range | single_date
    label: str = ""
    weekday: int | None = None  # 0 = Sunday
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None


@dataclass(frozen=True)
class DayRules:
    vegetarian: bool
    profile_diet: str
    avoided: tuple[FoodRef, ...] = ()
    # slot -> minutes since the empty-stomach dose; None when there is no such
    # medication or the slot falls before it.
    minutes_since_dose: dict[str, int | None] = field(default_factory=dict)
    # The day's requirement for the nutrients the mineral window cares about.
    requirement: dict[str, float] = field(default_factory=dict)


def nutrients_for(candidate: Candidate, grams: float) -> dict[str, float]:
    return {
        code: value * grams / 100.0 for code, value in candidate.per_100g.items()
    }


def sunday_index(day: datetime.date) -> int:
    """0 = Sunday, matching `observance_rules.weekday`. Python's weekday() has Monday = 0."""
    return (day.weekday() + 1) % 7


def vegetarian_reason(
    day: datetime.date, rules: Sequence[Observance]
) -> str | None:
    """Why this day is vegetarian, or None when no rule applies.

    The reason is shown next to the day, so a plan with no meat on it says which
    rule did that rather than looking like an oversight.
    """
    for rule in rules:
        if rule.kind == "weekday" and rule.weekday == sunday_index(day):
            return rule.label or f"your {day.strftime('%A')} rule"
        if (
            rule.kind == "date_range"
            and rule.start_date is not None
            and rule.end_date is not None
            and rule.start_date <= day <= rule.end_date
        ):
            return rule.label or "your observance"
        if rule.kind == "single_date" and rule.start_date == day:
            return rule.label or "your observance"
    return None


def allowed_by_diet(candidate: Candidate, rules: DayRules) -> bool:
    rank = DISH_DIET_RANK.get(candidate.diet, DISH_DIET_RANK["nonveg"])
    if rules.vegetarian:
        return rank == 0
    return rank <= PROFILE_DIET_RANK.get(rules.profile_diet, 0)


def _label_matches(label: str, candidate: Candidate) -> bool:
    needle = label.strip().lower()
    if not needle:
        return False
    return needle in candidate.name.lower() or any(
        needle in name.lower() for name in candidate.ingredient_names
    )


def _contains(candidate: Candidate, ref: FoodRef) -> bool:
    if ref.food_id is not None:
        if ref.food_kind == "dish":
            return ref.food_id == candidate.dish_id
        if ref.food_kind == "ingredient":
            return ref.food_id in candidate.ingredient_ids
        return False
    return _label_matches(ref.label, candidate)


def is_avoided(candidate: Candidate, avoided: Sequence[FoodRef]) -> bool:
    return any(_contains(candidate, ref) for ref in avoided)


def favourite_hits(
    candidate: Candidate, favourites: Sequence[FoodRef]
) -> tuple[str, ...]:
    return tuple(ref.label for ref in favourites if _contains(candidate, ref))


def _minutes(value: datetime.time) -> int:
    return value.hour * 60 + value.minute


def minutes_after(dose: datetime.time, slot_time: datetime.time) -> int | None:
    """Minutes from the dose to the slot, or None when the slot comes first."""
    gap = _minutes(slot_time) - _minutes(dose)
    return gap if gap >= 0 else None


def wait_until(slot_time: datetime.time, dose: datetime.time) -> datetime.time | None:
    """The earliest time to eat a slot that falls inside the 60-minute window."""
    gap = minutes_after(dose, slot_time)
    if gap is None or gap >= EMPTY_STOMACH_MINUTES:
        return None
    total = _minutes(dose) + EMPTY_STOMACH_MINUTES
    return datetime.time(total // 60 % 24, total % 60)


def is_mineral_heavy(candidate: Candidate, rules: DayRules) -> bool:
    totals = nutrients_for(candidate, candidate.default_grams)
    for code in MINERAL_WINDOW_NUTRIENTS:
        requirement = rules.requirement.get(code)
        if requirement and totals.get(code, 0.0) >= MINERAL_HEAVY_SHARE * requirement:
            return True
    return False


def candidates_for_slot(
    pool: Sequence[Candidate], slot: str, rules: DayRules
) -> list[Candidate]:
    """Every dish the day's constraints allow in this slot, in pool order."""
    minutes = rules.minutes_since_dose.get(slot)
    inside_window = minutes is not None and minutes < MINERAL_CLEARANCE_MINUTES
    return [
        candidate
        for candidate in pool
        if slot in candidate.slots
        and allowed_by_diet(candidate, rules)
        and not is_avoided(candidate, rules.avoided)
        and not (inside_window and is_mineral_heavy(candidate, rules))
    ]
