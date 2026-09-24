"""Weight-driven calorie recalibration.

The energy formula describes a population; a particular body burns somewhat more
or less than it says. Weekly weigh-ins are the only measurement the app has of
that difference, so when the trend drifts from the trajectory the goal implies,
the calorie target moves -- by a bounded step, and never below a floor.

Pure arithmetic over plain values. The weight service decides which weigh-ins
exist; this module decides what they mean.
"""

import datetime
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.nutrition_core.energy import (
    KCAL_PER_KG_BODY_FAT,
    SAFE_FLOOR_KCAL,
    Body,
    basal_metabolic_rate,
    energy_target,
    total_energy_expenditure,
)

# The mean of the last three weigh-ins: enough to average out a morning of water
# weight, few enough that a real change shows within a month of weighing weekly.
SMOOTHING_WEIGH_INS = 3

# A trend is read from at least three weigh-ins spanning at least two weeks, all
# inside the last four. A single week's change is mostly water.
TREND_WINDOW_DAYS = 28
MIN_TREND_WEIGH_INS = 3
MIN_TREND_SPAN_DAYS = 14

# Drift smaller than this sits inside the scatter of weekly weigh-ins.
DRIFT_TOLERANCE_KG_PER_WEEK = 0.25

# 1 kg/week of drift is ~1,100 kcal/day of imbalance. Half of it is corrected per
# step: a slope fitted to three or four points is noisy, and correcting noise in
# full overshoots the next time.
KCAL_PER_DAY_PER_KG_PER_WEEK = KCAL_PER_KG_BODY_FAT / 7.0
STEP_DAMPING = 0.5

# The spec's bound: the target stays within 10% of the formula, in total. Drift
# that 10% cannot absorb says the profile is wrong -- the activity level, most
# often -- and a larger correction would hide that rather than fix it.
MAX_OFFSET_SHARE = 0.10

# Offsets are kept to whole tens: "-210 kcal" is a statement, "-213.4" is noise.
OFFSET_STEP_KCAL = 10.0

# Below this a rate reads as "holding steady" in the copy.
STEADY_KG_PER_WEEK = 0.05


@dataclass(frozen=True)
class WeighIn:
    date: datetime.date
    weight_kg: float


@dataclass(frozen=True)
class Step:
    """A recalibration decision. `offset_kcal` is the new TOTAL offset, not the change."""

    offset_kcal: float
    expected_kg_per_week: float
    observed_kg_per_week: float
    reason: str


def smoothed_weight(weigh_ins: Sequence[WeighIn]) -> float | None:
    """The mean of the most recent weigh-ins, or None before the first."""
    recent = sorted(weigh_ins, key=lambda w: w.date)[-SMOOTHING_WEIGH_INS:]
    if not recent:
        return None
    return sum(w.weight_kg for w in recent) / len(recent)


def trend_points(
    weigh_ins: Sequence[WeighIn], as_of: datetime.date, since: datetime.date | None
) -> list[WeighIn]:
    """The weigh-ins a trend is read from.

    The last four weeks, and nothing before the most recent step: weigh-ins from
    before it were eaten against a different target, so they describe that one.
    The weigh-in on the step's own date stays in -- it is where the new target
    starts from.
    """
    start = as_of - datetime.timedelta(days=TREND_WINDOW_DAYS)
    if since is not None:
        start = max(start, since)
    return sorted((w for w in weigh_ins if start <= w.date <= as_of), key=lambda w: w.date)


def observed_rate(points: Sequence[WeighIn]) -> float | None:
    """Least-squares slope in kg/week, or None when there is too little to read.

    A fitted slope rather than last-minus-first, so one water-heavy morning at
    either end cannot decide the answer by itself.
    """
    ordered = sorted(points, key=lambda w: w.date)
    if len(ordered) < MIN_TREND_WEIGH_INS:
        return None
    if (ordered[-1].date - ordered[0].date).days < MIN_TREND_SPAN_DAYS:
        return None

    origin = ordered[0].date
    weeks = [(w.date - origin).days / 7.0 for w in ordered]
    weights = [w.weight_kg for w in ordered]
    mean_week = sum(weeks) / len(weeks)
    mean_weight = sum(weights) / len(weights)
    spread = sum((week - mean_week) ** 2 for week in weeks)
    covariance = sum(
        (week - mean_week) * (kg - mean_weight) for week, kg in zip(weeks, weights, strict=True)
    )
    return covariance / spread


def expected_rate(body: Body, goal: str, pace: str | None) -> float:
    """The kg/week the goal's formula target implies, from its real deficit.

    Derived from the energy gap rather than read off the pace, because the BMR
    clamp can shrink the deficit: a 55 kg sedentary woman on a steady loss sits
    on her BMR and can expect ~0.32 kg/week, not the 0.5 the pace names.
    """
    gap = energy_target(body, goal=goal, pace=pace) - total_energy_expenditure(body)
    return gap * 7.0 / KCAL_PER_KG_BODY_FAT


def lowest_target(body: Body, formula_kcal: float) -> float:
    """The floor a recalibration may not push below.

    The higher of BMR and the safe minimum -- unless the formula target is already
    under that, which `energy_target` allows only where maintenance itself is
    lower. Then the floor is the formula figure: recalibration may raise it, never
    take it lower.
    """
    return min(formula_kcal, max(basal_metabolic_rate(body), SAFE_FLOOR_KCAL[body.sex]))


def recalibrated_energy(body: Body, formula_kcal: float, offset_kcal: float) -> float:
    """The formula target moved by `offset_kcal`, inside the bound and above the floor."""
    bound = formula_kcal * MAX_OFFSET_SHARE
    clamped = max(-bound, min(bound, offset_kcal))
    return max(formula_kcal + clamped, lowest_target(body, formula_kcal))


def next_step(
    body: Body,
    goal: str,
    pace: str | None,
    current_offset_kcal: float,
    points: Sequence[WeighIn],
) -> Step | None:
    """The step the trend calls for, or None when it calls for none or none is possible."""
    observed = observed_rate(points)
    if observed is None:
        return None
    expected = expected_rate(body, goal, pace)
    drift = observed - expected
    if abs(drift) < DRIFT_TOLERANCE_KG_PER_WEEK:
        return None

    formula = energy_target(body, goal=goal, pace=pace)
    proposed = current_offset_kcal - drift * KCAL_PER_DAY_PER_KG_PER_WEEK * STEP_DAMPING
    applied = _whole_tens(recalibrated_energy(body, formula, proposed) - formula)
    current = recalibrated_energy(body, formula, current_offset_kcal) - formula
    if abs(applied - current) < OFFSET_STEP_KCAL:
        # Already at the bound or the floor: there is nowhere left to move.
        return None

    return Step(
        offset_kcal=applied,
        expected_kg_per_week=expected,
        observed_kg_per_week=observed,
        reason=_reason(expected, observed, lower=applied < current),
    )


def trend_note(
    body: Body,
    goal: str,
    pace: str | None,
    current_offset_kcal: float,
    points: Sequence[WeighIn],
    stepped_on: datetime.date | None,
) -> str | None:
    """One sentence on where the trend stands, for the weight screen."""
    observed = observed_rate(points)
    if observed is None:
        if stepped_on is not None:
            return (
                f"Your target last moved on {stepped_on.day} {stepped_on:%B}. The next reading "
                "needs three weigh-ins across at least two weeks after that."
            )
        return (
            "Your trend is read from three weigh-ins across at least two weeks. Weighing in "
            "once a week is enough."
        )

    drift = observed - expected_rate(body, goal, pace)
    if abs(drift) < DRIFT_TOLERANCE_KG_PER_WEEK:
        return "Your weight is tracking your goal, so your calorie target stays where it is."
    if next_step(body, goal, pace, current_offset_kcal, points) is not None:
        return None

    formula = energy_target(body, goal=goal, pace=pace)
    moved = abs(recalibrated_energy(body, formula, current_offset_kcal) - formula) >= 1.0
    direction = "down" if drift > 0 else "up"
    position = "above" if drift > 0 else "below"
    if moved:
        limit = f"your target has already moved as far {direction} as recalibration allows"
    else:
        # Nothing moved it: the formula itself sits on its floor.
        limit = f"your target is already as far {direction} as the app will set it"
    return (
        f"Your weight is running {position} your goal's trajectory, but {limit}. Check that "
        "the weight and activity level in your profile are right, and if the change is "
        "unexplained, mention it to your clinician."
    )


def _whole_tens(kcal: float) -> float:
    # Toward zero, so rounding can never carry an offset past its bound or floor.
    return math.trunc(kcal / OFFSET_STEP_KCAL) * OFFSET_STEP_KCAL


def _rate_words(rate: float) -> str:
    if abs(rate) < STEADY_KG_PER_WEEK:
        return "held steady"
    direction = "fallen" if rate < 0 else "risen"
    return f"{direction} about {abs(rate):.1f} kg a week"


def _goal_words(expected: float) -> str:
    if abs(expected) < STEADY_KG_PER_WEEK:
        return "a goal of holding steady"
    direction = "losing" if expected < 0 else "gaining"
    return f"a goal of {direction} about {abs(expected):.1f} kg a week"


def _reason(expected: float, observed: float, *, lower: bool) -> str:
    direction = "down" if lower else "up"
    return (
        f"Your weight has {_rate_words(observed)} against {_goal_words(expected)}, so your "
        f"calorie target moves {direction} a bounded step. It stays within 10% of what the "
        "formula gives and never goes below a safe floor."
    )
