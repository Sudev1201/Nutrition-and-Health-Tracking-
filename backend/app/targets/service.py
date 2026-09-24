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
from app.nutrition_core.energy import energy_target
from app.nutrition_core.recalibration import lowest_target
from app.nutrition_core.targets import (
    ENERGY_SCALED_REFERENCES,
    ReferenceValue,
    Target,
    build_targets,
)
from app.profiles import service as profiles
from app.weight import service as weight

# A carry reaches at most two days forward, so a day's targets are fully
# determined by the four days before it. Walking that window from a clean slate
# gives exact values without unbounded recursion into the user's whole history.
COMPENSATION_WINDOW_DAYS = 4

# ICMR-NIN 2020 publishes no postmenopausal category. The seed stores the IOM
# figure the spec falls back to as the female 60+ iron row, and a postmenopausal
# woman of any age reads that row -- for iron alone. Switching her whole band
# would drop the fourteen nutrients the 60+ band does not carry.
POSTMENOPAUSAL_IRON_BAND = "60+"
IOM_SOURCE = "IOM"

# After menopause there is no route to shed iron, so a day this close to the
# upper limit is worth a word before it becomes a habit.
IRON_LIMIT_SHARE = 0.8

# The targets that move with the weight-driven offset: energy itself, the
# macros `build_targets` derives from it, and the energy-scaled B vitamins. A
# window day whose offset differs from target_date's must be costed against
# its own figure for these -- never against target_date's stepped one.
_ENERGY_DERIVED_CODES = (
    frozenset({"energy", "fibre", "carbohydrate", "fat", "saturated_fat", "free_sugar"})
    | ENERGY_SCALED_REFERENCES
)


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

    references = {
        nutrient.code: ReferenceValue(ear=row.ear, rda=row.rda, ai=row.ai, source=row.source)
        for row, nutrient in rows
    }
    if _is_postmenopausal(profile) and band != POSTMENOPAUSAL_IRON_BAND:
        iron = _iron_reference(db, profile.sex, POSTMENOPAUSAL_IRON_BAND)
        if iron is not None:
            references["iron"] = iron
    return references


def _is_postmenopausal(profile: Profile) -> bool:
    return profile.sex == "female" and profile.menstrual_status == "postmenopausal"


def _iron_reference(db: Session, sex: str, band: str) -> ReferenceValue | None:
    row = db.scalars(
        select(RdaReference)
        .join(Nutrient, Nutrient.id == RdaReference.nutrient_id)
        .where(
            Nutrient.code == "iron",
            RdaReference.sex == sex,
            RdaReference.age_band == band,
            RdaReference.activity_level.is_(None),
        )
    ).one_or_none()
    if row is None:
        return None
    return ReferenceValue(ear=row.ear, rda=row.rda, ai=row.ai, source=row.source)


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
    floors: dict[str, float] | None = None,
) -> dict[str, NutrientPolicy]:
    floors = floors or {}
    policies = {}
    for code, target in targets.items():
        row = nutrients.get(code)
        compensable = bool(row and row.is_compensable) and code not in disabled
        policies[code] = NutrientPolicy(
            code=code,
            is_compensable=compensable,
            compensation_days=(row.compensation_days if row else 0) if compensable else 0,
            is_excess_sensitive=bool(row and row.is_excess_sensitive),
            # A floor the ledger may not lower past, where the target itself has no
            # EAR -- energy, whose floor is the one recalibration respects.
            ear=floors.get(code, target.ear),
            tul=target.tul,
            carry_cap_fraction=carry_cap_for(code),
        )
    return policies


def _recalibration_warnings(applied_offset_kcal: float) -> list[Warning]:
    """Say so whenever a recalibration has moved the energy target.

    Otherwise the calorie figure on Today changes with no explanation -- which
    reads as a bug, or worse, is trusted without being understood.
    """
    if abs(applied_offset_kcal) < 1.0:
        return []
    direction = "lower" if applied_offset_kcal < 0 else "higher"
    return [
        Warning(
            kind="calorie-recalibrated",
            message=(
                f"Your calorie target is {abs(round(applied_offset_kcal))} kcal {direction} "
                "than the formula gives, because your weigh-ins have drifted from your goal. "
                "The Weight screen has the detail."
            ),
        )
    ]


def _framework_warnings(references: dict[str, ReferenceValue]) -> list[Warning]:
    """The visible note the spec requires when iron is not ICMR's figure."""
    iron = references.get("iron")
    if iron is None or iron.source != IOM_SOURCE:
        return []
    figure = iron.rda if iron.rda is not None else iron.ai
    return [
        Warning(
            kind="reference-framework",
            message=(
                f"Your iron target is {figure:g} mg, the IOM figure for women after "
                "menopause. ICMR-NIN 2020 publishes no postmenopausal value, and its 29 mg "
                "figure for women averages menstrual loss, which no longer applies."
            ),
        )
    ]


def _iron_limit_warnings(
    references: dict[str, ReferenceValue],
    targets: dict[str, Target],
    consumed: dict[str, float],
) -> list[Warning]:
    """Flag a day's iron nearing the upper limit, for someone with no way to shed it."""
    reference = references.get("iron")
    iron = targets.get("iron")
    if reference is None or reference.source != IOM_SOURCE or iron is None or iron.tul is None:
        return []
    eaten = consumed.get("iron", 0.0)
    if eaten < iron.tul * IRON_LIMIT_SHARE:
        return []
    return [
        Warning(
            kind="approaching-limit",
            message=(
                f"Today's iron is {eaten:.0f} mg, close to the {iron.tul:g} mg upper limit. "
                "After menopause the body has no way to shed extra iron, so check "
                "supplements and fortified foods before adding more."
            ),
        )
    ]


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

    body = profiles.body_of(profile)
    formula = energy_target(body, goal=profile.goal, pace=profile.pace)
    references = load_references(db, profile)
    upper_limits = load_upper_limits(db)
    target_offset = weight.offset_on(db, user, target_date)
    base = build_targets(
        body,
        goal=profile.goal,
        pace=profile.pace,
        cereal_dominant=profile.cereal_dominant,
        references=references,
        upper_limits=upper_limits,
        # The recalibration in force on this date, so a past day keeps the target
        # it had and a step taken today does not re-cost yesterday.
        energy_offset_kcal=target_offset,
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
    # The ledger may lower energy after a surplus, but never through the floor a
    # recalibration respects. Carries from two surplus days add up, which without
    # this could take the day to 40% of its target -- far under BMR -- and the
    # planner sizes portions from that figure.
    policies = _policies(
        targets,
        nutrients,
        overlay.compensation_disabled,
        floors={"energy": lowest_target(body, formula)},
    )

    # Window days whose offset differs from target_date's need their own
    # energy-derived targets -- memoised by offset, since at most a couple of
    # distinct values occur inside a four-day window.
    offset_targets: dict[float, dict[str, Target]] = {target_offset: base}

    def _targets_for_offset(offset: float) -> dict[str, Target]:
        if offset not in offset_targets:
            offset_targets[offset] = build_targets(
                body,
                goal=profile.goal,
                pace=profile.pace,
                cereal_dominant=profile.cereal_dominant,
                references=references,
                upper_limits=upper_limits,
                energy_offset_kcal=offset,
            )
        return offset_targets[offset]

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
            # The offset in force on THIS day, not target_date's. A step taken
            # today must not re-cost a finished day that had a different (or no)
            # offset in force -- see `_ENERGY_DERIVED_CODES` above.
            day_offset = weight.offset_on(db, user, day)
            day_base = base if day_offset == target_offset else _targets_for_offset(day_offset)

            for code, target in targets.items():
                # The per-nutrient counterpart of the rule above. A code absent
                # from the totals was measured by none of the day's foods, so a
                # shortfall against it is a gap in the food tables rather than in
                # the diet -- and carrying it forward would invent a deficit the
                # user never had.
                if code not in consumed:
                    continue

                day_rda = target.rda
                if (
                    day_offset != target_offset
                    and code in _ENERGY_DERIVED_CODES
                    and target is base.get(code)
                ):
                    # Untouched by the condition overlay, so the offset is the
                    # only thing that moved it -- cost it at this day's figure.
                    day_rda = day_base[code].rda

                policy = policies[code]
                today_target = effective_target(policy, day_rda, carried[day][code])
                plan = plan_carry(
                    policy,
                    consumed=consumed.get(code, 0.0),
                    effective_target=today_target,
                    base_target=day_rda,
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
        warnings=[
            *overlay.warnings,
            *_recalibration_warnings(targets["energy"].rda - formula),
            *_framework_warnings(references),
            *_iron_limit_warnings(references, targets, consumed_today),
        ],
        hold_steady=overlay.compensation_disabled,
    )
