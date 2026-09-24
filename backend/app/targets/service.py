"""Resolve a user's targets for one day, and walk the compensation ledger.

This is where the pure `nutrition_core` functions meet the database: reference
rows in, a day's targets out, with the compensation ledger recomputed from the
diary rather than stored as a running total. `walk_ledger` is that
recomputation. Today reads one day of it through `resolve_day`; the weekly
report reads a whole week of it in one pass.
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
    SURPLUS_CARRY_DAYS,
    NutrientPolicy,
    carry_cap_for,
    effective_target,
    plan_carry,
)
from app.nutrition_core.conditions import OverlayResult, Warning, apply_conditions
from app.nutrition_core.energy import Body, energy_target
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
# day whose offset differs from the context date's must be costed against its
# own figure for these -- never against the context date's stepped one.
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


@dataclass(frozen=True)
class TargetContext:
    """Everything a day's targets are built from, loaded once per request.

    Only the recalibration offset changes from one day of a walk to the next, and
    `base_targets_on` reads that per day. The profile, the reference rows, the
    condition overlay and the ledger's policies are the context date's.
    """

    profile: Profile
    body: Body
    formula: float  # energy_target(body, goal, pace)
    references: dict[str, ReferenceValue]
    upper_limits: dict[str, float]
    # The targets at the context date, its warnings, and compensation_disabled.
    overlay: OverlayResult
    nutrients: dict[str, Nutrient]
    # Built with floors={"energy": lowest_target(body, formula)}.
    policies: dict[str, NutrientPolicy]
    # The offset in force on the context date, and `build_targets` at that
    # offset before the overlay. A target the overlay left alone is the very
    # object `built` holds, which is how `base_targets_on` tells a code only the
    # offset moved from one a condition set.
    energy_offset_kcal: float
    built: dict[str, Target]


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
        excess_sensitive = bool(row and row.is_excess_sensitive)
        compensation_days = (row.compensation_days if row else 0) if compensable else 0
        if compensable:
            # A surplus spreads over the days a shortfall would, as it always has.
            surplus_days = compensation_days
        elif excess_sensitive and code not in disabled:
            # Sodium, saturated fat, free sugar and cholesterol carry no shortfall,
            # but the spec still lowers the next two days after a surplus of them
            # (manual step 5). A lowered ceiling has no EAR to stop it, and that is
            # the point.
            surplus_days = SURPLUS_CARRY_DAYS
        else:
            # Excreted, unknown, or held steady: a surplus lowers nothing.
            surplus_days = 0
        policies[code] = NutrientPolicy(
            code=code,
            is_compensable=compensable,
            compensation_days=compensation_days,
            is_excess_sensitive=excess_sensitive,
            # A floor the ledger may not lower past, where the target itself has no
            # EAR -- energy, whose floor is the one recalibration respects.
            ear=floors.get(code, target.ear),
            tul=target.tul,
            carry_cap_fraction=carry_cap_for(code),
            surplus_days=surplus_days,
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


def _built_at(
    profile: Profile,
    body: Body,
    references: dict[str, ReferenceValue],
    upper_limits: dict[str, float],
    offset_kcal: float,
) -> dict[str, Target]:
    return build_targets(
        body,
        goal=profile.goal,
        pace=profile.pace,
        cereal_dominant=profile.cereal_dominant,
        references=references,
        upper_limits=upper_limits,
        energy_offset_kcal=offset_kcal,
    )


def load_context(db: Session, user: User, on_date: datetime.date) -> TargetContext | None:
    """What `on_date`'s targets are built from; None when there is no profile."""
    profile = profiles.get_profile(db, user)
    if profile is None:
        return None

    body = profiles.body_of(profile)
    formula = energy_target(body, goal=profile.goal, pace=profile.pace)
    references = load_references(db, profile)
    upper_limits = load_upper_limits(db)
    # The recalibration in force on this date, so a past day keeps the target it
    # had and a step taken today does not re-cost yesterday.
    offset = weight.offset_on(db, user, on_date)
    built = _built_at(profile, body, references, upper_limits, offset)

    overlay = apply_conditions(
        built,
        conditions=profiles.get_conditions(db, user),
        medications=[
            (item.name, item.taken_at.strftime("%H:%M"))
            for item in profiles.get_medications(db, user)
        ],
    )
    nutrients = load_nutrients(db)
    # The ledger may lower energy after a surplus, but never through the floor a
    # recalibration respects. Carries from two surplus days add up, which without
    # this could take the day to 40% of its target -- far under BMR -- and the
    # planner sizes portions from that figure.
    policies = _policies(
        overlay.targets,
        nutrients,
        overlay.compensation_disabled,
        floors={"energy": lowest_target(body, formula)},
    )
    return TargetContext(
        profile=profile,
        body=body,
        formula=formula,
        references=references,
        upper_limits=upper_limits,
        overlay=overlay,
        nutrients=nutrients,
        policies=policies,
        energy_offset_kcal=offset,
        built=built,
    )


def base_targets_on(
    db: Session, user: User, ctx: TargetContext, day: datetime.date
) -> dict[str, float]:
    """Each code's base target on `day`: its RDA, before anything is carried in.

    The context date's figures, except where a different recalibration offset
    was in force on `day`. Then the codes only the offset moves are rebuilt at
    that day's offset, so a step taken today does not re-cost a finished day that
    had a different (or no) offset in force. A code the condition overlay set
    keeps the context date's figure: the offset is not the only thing that moved
    it.
    """
    targets = ctx.overlay.targets
    offset = weight.offset_on(db, user, day)
    if offset == ctx.energy_offset_kcal:
        return {code: target.rda for code, target in targets.items()}

    own = _built_at(ctx.profile, ctx.body, ctx.references, ctx.upper_limits, offset)
    return {
        code: (
            own[code].rda
            if code in _ENERGY_DERIVED_CODES and target is ctx.built.get(code)
            else target.rda
        )
        for code, target in targets.items()
    }


@dataclass(frozen=True)
class LedgerDay:
    """One source day of a walk: what it was asked for, was carried, ate, and let expire."""

    date: datetime.date
    # Something was logged, and the day had ended (it is before `as_of`). An
    # untracked day hands nothing on and lets nothing expire.
    tracked: bool
    consumed: dict[str, float]  # {} when untracked
    base: dict[str, float]  # base_targets_on(day)
    # effective_target(policy, base, carried_in), for every code.
    effective: dict[str, float]
    carried_in: dict[str, float]
    carried_from: dict[str, datetime.date]
    # What could not be carried, >= 0. A code is present only when the day fell
    # short of it (or went over it); 0.0 means nothing was lost.
    expired_shortfall: dict[str, float]
    expired_surplus: dict[str, float]


@dataclass(frozen=True)
class Ledger:
    days: dict[datetime.date, LedgerDay]  # every day start..end inclusive
    # Per landing day, what was carried onto it and from which day first. Only
    # days something landed on appear, including those after `end`: the day
    # after a walk reads its carries here.
    carried: dict[datetime.date, dict[str, float]]
    sources: dict[datetime.date, dict[str, datetime.date]]


def walk_ledger(
    db: Session,
    user: User,
    ctx: TargetContext,
    start: datetime.date,
    end: datetime.date,
    as_of: datetime.date | None = None,
) -> Ledger:
    """Walk the source days `start`..`end`, handing each day's outcome forward.

    Each day is costed at its own base targets plus whatever earlier days of the
    walk carried onto it. Nothing is carried into `start`: the walk begins from a
    clean slate, which `COMPENSATION_WINDOW_DAYS` makes exact for the day Today
    asks about.

    `as_of` is the caller's today. A day on or after it has not ended, so like a
    day with nothing logged it is untracked: it carries nothing out and lets
    nothing expire.
    """
    from app.diary import service as diary  # imported here to avoid a cycle

    targets = ctx.overlay.targets
    carried: dict[datetime.date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    sources: dict[datetime.date, dict[str, datetime.date]] = defaultdict(dict)
    days: dict[datetime.date, LedgerDay] = {}

    day = start
    while day <= end:
        base = base_targets_on(db, user, ctx, day)
        # Carries only ever land on later days, so by now everything bound for
        # this one has arrived.
        carried_in = dict(carried.get(day, {}))
        effective = {
            code: effective_target(ctx.policies[code], base[code], carried_in.get(code, 0.0))
            for code in targets
        }

        # A day that has not ended yet is untracked for the same reason an empty
        # one is: what it holds so far is a part of a day, and costing it against
        # a whole day's target would carry a shortfall the user has all evening
        # to eat away.
        ended = as_of is None or day < as_of
        # A day with nothing logged is untracked, not a day of eating nothing.
        # Treating it as a total shortfall would flood every following day with
        # carries the user never earned.
        consumed = diary.consumed_on(db, user, day) if ended else {}

        expired_shortfall: dict[str, float] = {}
        expired_surplus: dict[str, float] = {}
        for code in targets:
            # The per-nutrient counterpart of the rule above. A code absent from
            # the totals was measured by none of the day's foods, so a shortfall
            # against it is a gap in the food tables rather than in the diet --
            # and carrying it forward would invent a deficit the user never had.
            if code not in consumed:
                continue

            plan = plan_carry(
                ctx.policies[code],
                consumed=consumed[code],
                effective_target=effective[code],
                base_target=base[code],
            )
            for carry in plan.carries:
                landing = day + datetime.timedelta(days=carry.day_offset)
                carried[landing][code] += carry.amount
                sources[landing].setdefault(code, day)

            delta = consumed[code] - effective[code]
            if delta < 0:
                expired_shortfall[code] = max(plan.expired, 0.0)
            elif delta > 0:
                expired_surplus[code] = max(plan.expired, 0.0)

        days[day] = LedgerDay(
            date=day,
            tracked=bool(consumed),
            consumed=consumed,
            base=base,
            effective=effective,
            carried_in=carried_in,
            carried_from=dict(sources.get(day, {})),
            expired_shortfall=expired_shortfall,
            expired_surplus=expired_surplus,
        )
        day += datetime.timedelta(days=1)

    return Ledger(
        days=days,
        carried={landing: dict(amounts) for landing, amounts in carried.items()},
        sources={landing: dict(codes) for landing, codes in sources.items()},
    )


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

    ctx = load_context(db, user, target_date)
    if ctx is None:
        return None

    # Everything that lands on `target_date` was handed on by the window before it.
    ledger = walk_ledger(
        db,
        user,
        ctx,
        target_date - datetime.timedelta(days=COMPENSATION_WINDOW_DAYS),
        target_date - datetime.timedelta(days=1),
        as_of,
    )
    carried = ledger.carried.get(target_date, {})
    sources = ledger.sources.get(target_date, {})

    consumed_today = diary.consumed_on(db, user, target_date)
    coverage_today = diary.coverage_on(db, user, target_date)
    targets = ctx.overlay.targets

    rows = []
    for code, target in sorted(targets.items()):
        nutrient = ctx.nutrients.get(code)
        carried_in = carried.get(code, 0.0)
        source_day = sources.get(code)

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
                target_effective=effective_target(ctx.policies[code], target.rda, carried_in),
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
            *ctx.overlay.warnings,
            *_recalibration_warnings(targets["energy"].rda - ctx.formula),
            *_framework_warnings(ctx.references),
            *_iron_limit_warnings(ctx.references, targets, consumed_today),
        ],
        hold_steady=ctx.overlay.compensation_disabled,
    )
