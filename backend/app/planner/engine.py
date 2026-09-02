"""The planner's construction and search. Pure, seeded, no database.

The spec's algorithm, in order: candidates are already filtered (rules.py),
then greedy construction scores each dish on how much of the day's weighted
nutrient gap it closes, portions are tuned to the slot's share of what the day
still needs, and a local search swaps out whichever item a better alternative
exists for until nothing improves. A seeded jitter keeps weeks from being
identical without making them irreproducible.
"""

import datetime
import random
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from app.meal_slots import SLOTS
from app.planner.rules import Candidate, FoodRef, Portion, favourite_hits, nutrients_for

# How a day's energy is usually shaped. A convention for sizing portions, not a
# target: nothing scores against these, they only decide how big each slot aims
# to be. Redistributed over the slots actually being planned.
SLOT_ENERGY_SHARE = {
    "breakfast": 0.25, "snack1": 0.10, "lunch": 0.30, "snack2": 0.10, "dinner": 0.25,
}

# Weights on the relative shortfall of each target. Energy and protein shape the
# day; the rest count once. Anything not listed weighs 1.0.
NUTRIENT_WEIGHTS = {"energy": 3.0, "protein": 2.0, "fibre": 1.5, "calcium": 1.5, "iron": 1.5}
DEFAULT_WEIGHT = 1.0
# Going over a ceiling (sodium, saturated fat) is worse than falling short of a target.
CEILING_WEIGHT = 2.0
# Crossing a tolerable upper limit is not a trade-off; it should never win.
UPPER_LIMIT_PENALTY = 10.0

# Variety: each earlier use of a dish this week, and using it two days running.
REPEAT_PENALTY = 0.15
CONSECUTIVE_DAY_PENALTY = 0.25
FAVOURITE_BONUS = 0.10
# Enough to reorder near-ties, not enough to override a real nutrient difference.
JITTER = 0.05

# On warfarin, vitamin K should move no more than this share of its goal from one
# day to the next. Beyond it, the swing is costed like a shortfall.
HOLD_STEADY_TOLERANCE = 0.25
HOLD_STEADY_PENALTY = 1.0

LOCAL_SEARCH_PASSES = 2
# A dish earns a "covers N% of ..." line only when it does real work.
RATIONALE_MIN_CLOSURE = 0.10


@dataclass(frozen=True)
class NutrientGoal:
    code: str
    display_name: str
    amount: float  # the day's effective target, or its ceiling
    kind: str  # target | ceiling
    tul: float | None = None


@dataclass(frozen=True)
class PlannedItem:
    slot: str
    dish_id: uuid.UUID
    dish_name: str
    portion: Portion
    nutrients: dict[str, float]
    favourites: tuple[str, ...] = ()
    rationale: str | None = None
    locked: bool = False


@dataclass(frozen=True)
class DayInput:
    """Everything the engine needs to plan one day."""

    date: datetime.date
    goals: dict[str, NutrientGoal]
    # The slots to fill, each with the dishes the rules allow there.
    slots: dict[str, tuple[Candidate, ...]]
    # Locked items: kept exactly as they are, and counted toward the day.
    fixed: tuple[PlannedItem, ...] = ()
    # Food already logged today: counted, so the plan covers what is left.
    consumed: dict[str, float] = field(default_factory=dict)
    favourites: tuple[FoodRef, ...] = ()
    hold_steady: frozenset[str] = frozenset()
    # Yesterday's totals, for hold_steady. plan_week fills this in from the day
    # before; the caller sets it for the first day of a run.
    previous_day: dict[str, float] | None = None
    # Dishes already eaten today: not offered again while anything else fits,
    # released by the too-small-pool fallback below rather than left as a hole.
    eaten: frozenset[uuid.UUID] = frozenset()


def add_totals(*parts: dict[str, float]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for part in parts:
        for code, value in part.items():
            totals[code] = totals.get(code, 0.0) + value
    return totals


def weighted_gap(totals: dict[str, float], goals: dict[str, NutrientGoal]) -> float:
    """How far a day is from its goals, as one number. Zero is a perfect day."""
    gap = 0.0
    for goal in goals.values():
        if goal.amount <= 0:
            continue
        have = totals.get(goal.code, 0.0)
        if goal.kind == "ceiling":
            gap += CEILING_WEIGHT * max(0.0, have / goal.amount - 1.0)
        else:
            weight = NUTRIENT_WEIGHTS.get(goal.code, DEFAULT_WEIGHT)
            gap += weight * max(0.0, 1.0 - have / goal.amount)
        if goal.tul is not None and have > goal.tul:
            gap += UPPER_LIMIT_PENALTY * (have / goal.tul - 1.0)
    return gap


def _hold_steady_penalty(totals: dict[str, float], day: DayInput) -> float:
    if not day.hold_steady or day.previous_day is None:
        return 0.0
    penalty = 0.0
    for code in day.hold_steady:
        goal = day.goals.get(code)
        if goal is None or goal.amount <= 0:
            continue
        swing = abs(totals.get(code, 0.0) - day.previous_day.get(code, 0.0)) / goal.amount
        penalty += HOLD_STEADY_PENALTY * max(0.0, swing - HOLD_STEADY_TOLERANCE)
    return penalty


def day_cost(totals: dict[str, float], day: DayInput) -> float:
    return weighted_gap(totals, day.goals) + _hold_steady_penalty(totals, day)


def energy_budget(
    day: DayInput,
    slot: str,
    placed_totals: dict[str, float],
    open_slots: Sequence[str],
) -> float:
    """This slot's share of the energy the day still needs.

    Whatever is already placed -- logged food, locked items, slots planned so
    far -- comes off the top, and the remainder is split over the slots still
    open by their usual shares. Re-planning dinner after a big lunch therefore
    plans a small dinner rather than a second full day.
    """
    energy = day.goals.get("energy")
    if energy is None or slot not in open_slots:
        return 0.0
    remaining = max(0.0, energy.amount - placed_totals.get("energy", 0.0))
    share_total = sum(SLOT_ENERGY_SHARE[s] for s in open_slots) or 1.0
    return remaining * SLOT_ENERGY_SHARE[slot] / share_total


def portion_for(candidate: Candidate, budget: float) -> Portion:
    """The rung of the dish's portion ladder whose energy is closest to the budget."""
    per_100g = candidate.per_100g.get("energy", 0.0)
    return min(candidate.portions, key=lambda p: abs(per_100g * p.grams / 100.0 - budget))


def _make_item(
    candidate: Candidate, portion: Portion, slot: str, favourites: Sequence[FoodRef]
) -> PlannedItem:
    return PlannedItem(
        slot=slot,
        dish_id=candidate.dish_id,
        dish_name=candidate.name,
        portion=portion,
        nutrients=nutrients_for(candidate, portion.grams),
        favourites=favourite_hits(candidate, favourites),
    )


def _choose_for_slot(
    day: DayInput,
    slot: str,
    placed_totals: dict[str, float],
    open_slots: Sequence[str],
    uses: Counter,
    yesterday: frozenset[uuid.UUID],
    rng: random.Random,
    exclude: frozenset[uuid.UUID],
) -> PlannedItem | None:
    """The best dish for one slot, given everything already on the day."""
    budget = energy_budget(day, slot, placed_totals, open_slots)
    before = day_cost(placed_totals, day)

    best: PlannedItem | None = None
    best_score = float("-inf")
    for candidate in day.slots.get(slot, ()):
        if candidate.dish_id in exclude:
            continue
        item = _make_item(candidate, portion_for(candidate, budget), slot, day.favourites)

        score = before - day_cost(add_totals(placed_totals, item.nutrients), day)
        score -= REPEAT_PENALTY * uses[candidate.dish_id]
        if candidate.dish_id in yesterday:
            score -= CONSECUTIVE_DAY_PENALTY
        if item.favourites:
            score += FAVOURITE_BONUS
        score += rng.uniform(-JITTER, JITTER)

        if score > best_score:
            best, best_score = item, score
    return best


def explain(
    day: DayInput,
    fixed_totals: dict[str, float],
    items: dict[str, PlannedItem],
    slot: str,
) -> str | None:
    """Why this dish: the target it does most for, and any favourite it carries.

    Null when neither applies. The plan should not be a black box, but a reason
    that says nothing ("adds some energy") is worse than no reason.
    """
    item = items[slot]
    without = add_totals(fixed_totals, *(i.nutrients for s, i in items.items() if s != slot))

    best_code, best_closure = None, 0.0
    for code, goal in day.goals.items():
        if goal.kind != "target" or goal.amount <= 0:
            continue
        gap_before = max(0.0, goal.amount - without.get(code, 0.0))
        closed = min(item.nutrients.get(code, 0.0), gap_before) / goal.amount
        if closed > best_closure:
            best_code, best_closure = code, closed

    parts = []
    if best_code is not None and best_closure >= RATIONALE_MIN_CLOSURE:
        name = day.goals[best_code].display_name.lower()
        parts.append(f"Covers {round(best_closure * 100)}% of the day's {name}")
    if item.favourites:
        parts.append(f"Has {item.favourites[0]}, which you like")
    return ". ".join(parts) or None


def plan_day(
    day: DayInput,
    rng: random.Random,
    uses: Counter | None = None,
    yesterday: frozenset[uuid.UUID] = frozenset(),
) -> list[PlannedItem]:
    """Fill the day's open slots: greedy in eating order, then local search."""
    uses = Counter() if uses is None else uses
    fixed_totals = add_totals(day.consumed, *(item.nutrients for item in day.fixed))
    open_slots = [s for s in SLOTS if day.slots.get(s)]
    fixed_dishes = frozenset(item.dish_id for item in day.fixed)

    items: dict[str, PlannedItem] = {}
    for index, slot in enumerate(open_slots):
        placed = add_totals(fixed_totals, *(i.nutrients for i in items.values()))
        used_today = fixed_dishes | day.eaten | frozenset(i.dish_id for i in items.values())
        chosen = _choose_for_slot(
            day, slot, placed, open_slots[index:], uses, yesterday, rng, exclude=used_today
        )
        if chosen is None:
            # A pool too small to avoid a repeat is better than an empty slot.
            chosen = _choose_for_slot(
                day, slot, placed, open_slots[index:], uses, yesterday, rng, exclude=frozenset()
            )
        if chosen is not None:
            items[slot] = chosen

    # Local search: replace any item whose best alternative lowers the day's
    # cost, holding the rest fixed. Acceptance is on the true cost, so the jitter
    # only decides which alternative is proposed, never whether it is taken.
    for _ in range(LOCAL_SEARCH_PASSES):
        improved = False
        for slot in list(items):
            others = {s: i for s, i in items.items() if s != slot}
            base = add_totals(fixed_totals, *(i.nutrients for i in others.values()))
            current = day_cost(add_totals(base, items[slot].nutrients), day)
            exclude = fixed_dishes | day.eaten | frozenset(i.dish_id for i in others.values())
            exclude |= {items[slot].dish_id}
            alternative = _choose_for_slot(
                day, slot, base, [slot], uses, yesterday, rng, exclude=exclude
            )
            if alternative is not None and (
                day_cost(add_totals(base, alternative.nutrients), day) < current - 1e-9
            ):
                items[slot] = alternative
                improved = True
        if not improved:
            break

    return [
        replace(items[slot], rationale=explain(day, fixed_totals, items, slot))
        for slot in SLOTS
        if slot in items
    ]


def plan_week(
    days: Sequence[DayInput],
    rng: random.Random,
    history: Counter | None = None,
    yesterday: frozenset[uuid.UUID] = frozenset(),
) -> list[list[PlannedItem]]:
    """Plan consecutive days, carrying variety and yesterday's totals forward.

    `history` seeds the repetition counter with dishes already on the week's
    earlier, unplanned days; `yesterday` is the dish set of the day before the
    first one here.
    """
    uses = Counter() if history is None else Counter(history)
    previous_totals: dict[str, float] | None = None
    week: list[list[PlannedItem]] = []

    for day in days:
        if day.previous_day is None and previous_totals is not None:
            day = replace(day, previous_day=previous_totals)

        items = plan_day(day, rng, uses, yesterday)

        for item in [*items, *day.fixed]:
            uses[item.dish_id] += 1
        yesterday = frozenset(item.dish_id for item in [*items, *day.fixed])
        previous_totals = add_totals(
            day.consumed, *(i.nutrients for i in items), *(i.nutrients for i in day.fixed)
        )
        week.append(items)

    return week


def alternative_for(
    day: DayInput,
    slot: str,
    rng: random.Random,
    exclude: frozenset[uuid.UUID],
) -> PlannedItem | None:
    """For a swap: the best replacement for one slot with the rest of the day fixed.

    `day.fixed` carries the other items of the day; `day.slots` holds only the
    slot being swapped. Dishes already on the day are excluded along with the
    caller's own exclusions (at least the dish being swapped away).
    """
    fixed_totals = add_totals(day.consumed, *(item.nutrients for item in day.fixed))
    used = exclude | day.eaten | frozenset(item.dish_id for item in day.fixed)
    chosen = _choose_for_slot(day, slot, fixed_totals, [slot], Counter(), frozenset(), rng, used)
    if chosen is None:
        return None
    items = {item.slot: item for item in day.fixed} | {slot: chosen}
    return replace(chosen, rationale=explain(day, day.consumed, items, slot))
