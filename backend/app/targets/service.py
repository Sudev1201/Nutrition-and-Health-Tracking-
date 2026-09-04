"""Resolve a user's targets for one day.

This is where the pure `nutrition_core` functions meet the database: reference
rows in, a day's targets out, with the compensation ledger recomputed from the
diary rather than stored as a running total.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient
from app.models.profile import Profile
from app.models.reference import RdaReference, UpperLimit
from app.models.user import User
from app.nutrition_core.compensation import (
    NutrientPolicy,
    carry_cap_for,
    effective_target,
    plan_carry,
)
from app.nutrition_core.conditions import Warning, apply_conditions
from app.nutrition_core.energy import Body
from app.nutrition_core.targets import ReferenceValue, Target, build_targets
from app.profiles import service as profiles

# A carry reaches at most two days forward, so a day's targets are fully
# determined by the four days before it. Walking that window from a clean slate
# gives exact values without unbounded recursion into the user's whole history.
COMPENSATION_WINDOW_DAYS = 4


@dataclass(frozen=True)
class NutrientDay:
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    ear: float | None
    rda: float
    tul: float | None
    target_effective: float
    carried_in: float
    carried_from: str | None
    consumed: float
    # The share of the day's food weight that actually carried a figure for this
    # nutrient. 0.0 means nothing measured it, so `consumed` is silence rather
    # than zero -- the distinction the ledger below depends on.
    coverage: float


@dataclass(frozen=True)
class DayTargets:
    date: datetime.date
    nutrients: list[NutrientDay]
    warnings: list[Warning]
    # Nutrients whose day-to-day variation must NOT be smoothed -- vitamin K on
    # warfarin. The ledger already honours this through `_policies`; the planner
    # reads it here so "hold steady" is decided in one place.
    hold_steady: frozenset[str] = frozenset()


def age_band(age: int) -> str:
    """Matches `rda_reference.age_band`. Only calcium, vitamin D and iron differ."""
    return "60+" if age >= 60 else "18-59"


def load_references(db: Session, profile: Profile) -> dict[str, ReferenceValue]:
    """Reference rows for this user's sex, age band and activity level.

    Thiamine, riboflavin, niacin and B6 are energy-scaled and stored per
    activity level; everything else has a null `activity_level`. Taking the
    headline (moderate) figures for a sedentary user over-targets those four by
    roughly 25%, so the activity match is not optional.
    """
    band = age_band(profile.age)
    rows = db.execute(
        select(RdaReference, Nutrient)
        .join(Nutrient, Nutrient.id == RdaReference.nutrient_id)
        .where(
            RdaReference.sex == profile.sex,
            RdaReference.age_band == band,
            # `activity_level IN (:activity, NULL)` is never true for a NULL row
            # -- SQL's three-valued logic makes `NULL IN (...)` evaluate to NULL,
            # not true. Written as an explicit IS NULL branch, because the first
            # form silently dropped every nutrient without an activity dimension
            # (calcium, sodium, B12 -- most of them) from the targets.
            or_(
                RdaReference.activity_level == profile.activity,
                RdaReference.activity_level.is_(None),
            ),
        )
    ).all()

    return {
        nutrient.code: ReferenceValue(ear=row.ear, rda=row.rda, ai=row.ai)
        for row, nutrient in rows
    }


def load_upper_limits(db: Session) -> dict[str, float]:
    """Dietary limits only.

    Magnesium's 350 mg limit is for supplements and explicitly excludes food and
    water — warning on dietary magnesium would be a bug, so those rows are left
    out entirely rather than filtered downstream.
    """
    rows = db.execute(
        select(UpperLimit, Nutrient)
        .join(Nutrient, Nutrient.id == UpperLimit.nutrient_id)
        .where(UpperLimit.supplemental_only.is_(False))
    ).all()
    return {nutrient.code: row.value for row, nutrient in rows}


def load_nutrients(db: Session) -> dict[str, Nutrient]:
    return {nutrient.code: nutrient for nutrient in db.scalars(select(Nutrient))}


def _policies(
    targets: dict[str, Target],
    nutrients: dict[str, Nutrient],
    disabled: frozenset[str],
) -> dict[str, NutrientPolicy]:
    policies = {}
    for code, target in targets.items():
        row = nutrients.get(code)
        compensable = bool(row and row.is_compensable) and code not in disabled
        policies[code] = NutrientPolicy(
            code=code,
            is_compensable=compensable,
            compensation_days=(row.compensation_days if row else 0) if compensable else 0,
            is_excess_sensitive=bool(row and row.is_excess_sensitive),
            ear=target.ear,
            tul=target.tul,
            carry_cap_fraction=carry_cap_for(code),
        )
    return policies


def resolve_day(
    db: Session,
    user: User,
    target_date: datetime.date,
    as_of: datetime.date | None = None,
) -> DayTargets | None:
    """Targets for one day, with the ledger recomputed from the diary.

    `as_of` is the caller's today: the day in progress is not a finished day, so
    it earns no carry. Without it, a breakfast-only log at 10 a.m. reads as a
    whole day's shortfall and inflates tomorrow's goals by the rest of today.
    The targets screen leaves it unset -- it asks about one day at a time, and
    the days before today have all ended.
    """
    from app.diary import service as diary  # imported here to avoid a cycle

    profile = profiles.get_profile(db, user)
    if profile is None:
        return None

    body = Body(
        sex=profile.sex,
        age=profile.age,
        weight_kg=profile.weight_kg,
        activity=profile.activity,
    )
    base = build_targets(
        body,
        goal=profile.goal,
        pace=profile.pace,
        cereal_dominant=profile.cereal_dominant,
        references=load_references(db, profile),
        upper_limits=load_upper_limits(db),
    )

    overlay = apply_conditions(
        base,
        conditions=profiles.get_conditions(db, user),
        medications=[
            (item.name, item.taken_at.strftime("%H:%M"))
            for item in profiles.get_medications(db, user)
        ],
    )
    targets = overlay.targets
    nutrients = load_nutrients(db)
    policies = _policies(targets, nutrients, overlay.compensation_disabled)

    # Walk the window forward, accumulating what each day hands to the next.
    carried: dict[datetime.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    sources: dict[datetime.date, dict[str, datetime.date]] = defaultdict(dict)

    start = target_date - datetime.timedelta(days=COMPENSATION_WINDOW_DAYS)
    day = start
    while day < target_date:
        # A day that has not ended yet is untracked for the same reason an empty
        # one is: what it holds so far is a part of a day, and costing it against
        # a whole day's target would carry a shortfall the user has all evening
        # to eat away.
        if as_of is not None and day >= as_of:
            day += datetime.timedelta(days=1)
            continue

        consumed = diary.consumed_on(db, user, day)

        # A day with nothing logged is untracked, not a day of eating nothing.
        # Treating it as a total shortfall would flood every following day with
        # carries the user never earned.
        if consumed:
            for code, target in targets.items():
                # The per-nutrient counterpart of the rule above. A code absent
                # from the totals was measured by none of the day's foods, so a
                # shortfall against it is a gap in the food tables rather than in
                # the diet -- and carrying it forward would invent a deficit the
                # user never had.
                if code not in consumed:
                    continue

                policy = policies[code]
                today_target = effective_target(policy, target.rda, carried[day][code])
                plan = plan_carry(
                    policy,
                    consumed=consumed.get(code, 0.0),
                    effective_target=today_target,
                    base_target=target.rda,
                )
                for carry in plan.carries:
                    landing = day + datetime.timedelta(days=carry.day_offset)
                    carried[landing][code] += carry.amount
                    sources[landing].setdefault(code, day)
        day += datetime.timedelta(days=1)

    consumed_today = diary.consumed_on(db, user, target_date)
    coverage_today = diary.coverage_on(db, user, target_date)

    rows = []
    for code, target in sorted(targets.items()):
        nutrient = nutrients.get(code)
        carried_in = carried[target_date].get(code, 0.0)
        source_day = sources[target_date].get(code)

        rows.append(
            NutrientDay(
                code=code,
                display_name=nutrient.display_name if nutrient else code,
                unit=nutrient.unit if nutrient else "g",
                category=nutrient.category if nutrient else "macro",
                kind=target.kind,
                ear=target.ear,
                rda=target.rda,
                tul=target.tul,
                target_effective=effective_target(policies[code], target.rda, carried_in),
                carried_in=carried_in,
                carried_from=source_day.strftime("%A") if source_day else None,
                consumed=consumed_today.get(code, 0.0),
                coverage=coverage_today.get(code, 0.0),
            )
        )

    return DayTargets(
        date=target_date,
        nutrients=rows,
        warnings=overlay.warnings,
        hold_steady=overlay.compensation_disabled,
    )
