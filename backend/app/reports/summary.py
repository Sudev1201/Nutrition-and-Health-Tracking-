"""The weekly report's arithmetic: what counts as met, what was never made up, what to eat.

Pure functions over plain data: no database, no HTTP. `app.reports.service` walks the
ledger and reads the diary, then hands this module one `DayFacts` per elapsed, tracked
day. A day still in progress, or one with nothing logged, never reaches it -- so neither
can read as a day of eating nothing.

Every figure is over *measured* days only. A nutrient no logged food carried a figure
for is a gap in the food tables, not in the diet, and must never read as a deficit.
"""

import datetime
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.planner.rules import (
    Candidate,
    DayRules,
    FoodRef,
    allowed_by_diet,
    is_avoided,
    nutrients_for,
)

# An expiry under this share of the week's target is rounding in the ledger, not a
# gap worth a line of the report.
UNCOMPENSATED_MIN_SHARE = 0.01
# Reference intakes are averages "over 1 or more weeks", so a week that reached 90% of
# its summed target is close enough: a suggestion for a near miss is noise.
SUGGESTION_SHORTFALL_SHARE = 0.90
# With under half the food weight measured, a low total says more about the food
# tables than about the diet.
SUGGESTION_MIN_COVERAGE = 0.5
SUGGESTION_MIN_DAYS = 3
MAX_SUGGESTED_NUTRIENTS = 3
MAX_SUGGESTED_FOODS = 3
# Telling someone losing weight that calories were "not made up", or that they should
# eat more of them, works against their goal.
EXCLUDED_FROM_GAPS = frozenset({"energy"})

# The report reads macros, then minerals, then vitamins.
CATEGORY_RANK = {"macro": 0, "mineral": 1, "vitamin": 2}

PROTEIN_REASON = "Protein has no storage pool, so a short day is not carried forward."


@dataclass(frozen=True)
class NutrientMeta:
    """What the report needs to know about a nutrient besides its figures."""

    code: str
    display_name: str
    unit: str
    category: str  # macro | mineral | vitamin
    kind: str  # target | ceiling, as the targets give it
    # The nutrients table's own flag: false when the body has no store to draw on.
    is_compensable: bool
    carry_cap_fraction: float


@dataclass(frozen=True)
class DayFacts:
    """One elapsed, tracked day, as the report sees it."""

    date: datetime.date
    consumed: dict[str, float]
    coverage: dict[str, float]  # 0 < share <= 1 for measured codes; absent = not measured
    base: dict[str, float]
    ear: dict[str, float | None]
    effective: dict[str, float]
    tul: dict[str, float | None]
    expired_shortfall: dict[str, float]


@dataclass(frozen=True)
class NutrientWeek:
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    measured_days: int
    target_total: float  # sum of base over measured days
    ear_total: float | None  # sum of ear over measured days; None if the nutrient has no EAR
    consumed_total: float  # sum over measured days
    days_met: int
    days_over_limit: int
    coverage: float  # mean coverage over measured days (0 when none)


@dataclass(frozen=True)
class Gap:
    code: str
    display_name: str
    unit: str
    amount: float
    reason_code: str  # not_compensable | cap
    reason: str


def is_met(
    kind: str, consumed: float, ear: float | None, effective: float, tul: float | None
) -> bool:
    """Whether one measured day was in Today's "on target" band for a nutrient.

    A target nutrient is met from its EAR -- the adequacy floor ICMR plans an
    individual's diet against -- or from its effective target where there is no EAR.
    Going over the target is not a miss; reaching the upper limit is. A ceiling is met
    under the day's effective ceiling, which a harmful surplus the day before may
    have lowered.
    """
    # Reaching a limit exactly is already "above the limit" on Today (status.ts reads
    # consumed >= limit that way), so it is not met here either.
    if kind == "ceiling":
        return consumed < effective
    floor = ear if ear is not None else effective
    return consumed >= floor and (tul is None or consumed < tul)


def summarise(days: Sequence[DayFacts], meta: dict[str, NutrientMeta]) -> list[NutrientWeek]:
    """One row per nutrient measured on at least one day, in the report's order.

    Weekly sums are never compared with a daily limit: a day over the upper limit is
    counted as such, on its own.
    """
    weeks = []
    for code, info in meta.items():
        # A code with no target that day has nothing to be measured against.
        measured = [d for d in days if code in d.base and d.coverage.get(code, 0.0) > 0]
        if not measured:
            continue
        weeks.append(
            NutrientWeek(
                code=code,
                display_name=info.display_name,
                unit=info.unit,
                category=info.category,
                kind=info.kind,
                measured_days=len(measured),
                # The base target, before carries. A shortfall made up later raised
                # that later day's effective target, so summing effective targets
                # would count the one shortfall twice.
                target_total=sum(d.base[code] for d in measured),
                ear_total=_ear_total(measured, code),
                consumed_total=sum(d.consumed.get(code, 0.0) for d in measured),
                days_met=sum(_met_on(d, code, info.kind) for d in measured),
                days_over_limit=sum(_over_limit(d, code) for d in measured),
                coverage=sum(d.coverage[code] for d in measured) / len(measured),
            )
        )
    return sorted(
        weeks, key=lambda w: (CATEGORY_RANK.get(w.category, len(CATEGORY_RANK)), w.display_name)
    )


def uncompensated(
    days: Sequence[DayFacts], meta: dict[str, NutrientMeta], held_steady: frozenset[str]
) -> list[Gap]:
    """The shortfalls the ledger could not carry, per nutrient, as the spec requires.

    Target nutrients only: the ledger records a low-sodium day as an expired
    shortfall, but a low-sodium day is not a shortfall. Energy is left out (see
    EXCLUDED_FROM_GAPS), and so is anything held steady -- vitamin K on an
    anticoagulant is not averaged by design, so its expiry is the rule working.
    """
    skipped = EXCLUDED_FROM_GAPS | held_steady
    gaps = []
    for week in summarise(days, meta):
        info = meta[week.code]
        if info.kind != "target" or week.code in skipped:
            continue
        amount = sum(d.expired_shortfall.get(week.code, 0.0) for d in days)
        if amount <= 0 or amount < UNCOMPENSATED_MIN_SHARE * week.target_total:
            continue
        reason_code, reason = _reason(info)
        gaps.append(
            Gap(
                code=week.code,
                display_name=week.display_name,
                unit=week.unit,
                amount=amount,
                reason_code=reason_code,
                reason=reason,
            )
        )
    return gaps


def nutrients_to_suggest(
    weeks: Sequence[NutrientWeek], tracked_days: int, excluded: frozenset[str]
) -> list[NutrientWeek]:
    """The nutrients worth building next week around, worst first.

    Only a shortfall the diary can vouch for: measured on at least half the tracked
    days (and at least three), with at least half the food weight carrying a figure.
    `excluded` is the caller's safety list -- whatever is held steady, and potassium on
    a potassium-sparing drug -- and is never pushed, however short it looks.
    """
    min_days = max(SUGGESTION_MIN_DAYS, math.ceil(tracked_days / 2))
    skipped = excluded | EXCLUDED_FROM_GAPS
    short = [
        week
        for week in weeks
        if week.kind == "target"
        and week.code not in skipped
        and week.measured_days >= min_days
        and week.coverage >= SUGGESTION_MIN_COVERAGE
        and week.consumed_total < SUGGESTION_SHORTFALL_SHARE * week.target_total
    ]
    # The filter above keeps target_total > 0, so the ratio is always defined.
    short.sort(key=lambda week: (week.consumed_total / week.target_total, week.display_name))
    return short[:MAX_SUGGESTED_NUTRIENTS]


def foods_for(
    code: str, pool: Sequence[Candidate], profile_diet: str, avoided: Sequence[FoodRef]
) -> list[Candidate]:
    """Dishes carrying the most of a nutrient per default portion, that this person eats.

    The diet and the avoided foods are the planner's own hard constraints, so a
    suggestion can never name a dish the plan would refuse. Observance days are left
    to the plan: the suggestion is for the week, not for one day of it. A dish name
    already chosen is not repeated -- a household member's copy of a dish is still
    the same dish to the reader.
    """
    rules = DayRules(vegetarian=False, profile_diet=profile_diet, avoided=tuple(avoided))
    carrying = [
        (nutrients_for(candidate, candidate.default_grams).get(code, 0.0), candidate)
        for candidate in pool
        if allowed_by_diet(candidate, rules) and not is_avoided(candidate, rules.avoided)
    ]
    ranked = sorted(
        ((amount, candidate) for amount, candidate in carrying if amount > 0),
        key=lambda pair: (-pair[0], pair[1].name.casefold()),
    )

    chosen: list[Candidate] = []
    names: set[str] = set()
    for _, candidate in ranked:
        name = candidate.name.casefold()
        if name in names:
            continue
        names.add(name)
        chosen.append(candidate)
        if len(chosen) == MAX_SUGGESTED_FOODS:
            break
    return chosen


def suggestion_text(week: NutrientWeek, foods: Sequence[Candidate]) -> str:
    """One plain sentence, or two: never a medication change, never a dose."""
    # "fell short this week" is true of every nutrient the rule picks; "most days" is
    # not -- two very low days in an adequate week qualify.
    lead = f"{week.display_name} fell short this week."
    if not foods:
        return lead
    # Names are listed as they are spelled, never re-cased mid-sentence: "Mysore
    # masala dosa" must not become "mysore masala dosa".
    return f"{lead} Dishes that carry it: {', '.join(food.name for food in foods)}."


def _ear_total(days: Sequence[DayFacts], code: str) -> float | None:
    total = 0.0
    for day in days:
        ear = day.ear.get(code)
        if ear is None:
            return None
        total += ear
    return total


def _met_on(day: DayFacts, code: str, kind: str) -> bool:
    return is_met(
        kind,
        day.consumed.get(code, 0.0),
        day.ear.get(code),
        day.effective.get(code, day.base[code]),
        day.tul.get(code),
    )


def _over_limit(day: DayFacts, code: str) -> bool:
    tul = day.tul.get(code)
    return tul is not None and day.consumed.get(code, 0.0) >= tul


def _reason(info: NutrientMeta) -> tuple[str, str]:
    if not info.is_compensable:
        if info.code == "protein":
            return "not_compensable", PROTEIN_REASON
        reason = (
            f"{info.display_name} is not carried forward: the body has no store of it to draw on."
        )
        return "not_compensable", reason
    percent = round(info.carry_cap_fraction * 100)
    return "cap", f"Beyond the {percent}% a day can carry, so it expired."
