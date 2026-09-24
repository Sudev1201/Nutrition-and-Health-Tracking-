"""The weekly report: what a week added up to, and what to eat more of next.

Derived on demand from the diary, the ledger walk and the plan, and never
stored, so there is nothing to go stale. An old week is re-costed against the
current profile and food tables, which is a recorded gap. The arithmetic
belongs to `summary`, which never sees a Session; this module gathers its
inputs.
"""

import datetime
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.diary import service as diary
from app.meal_slots import SLOTS
from app.models.diary import MealLog
from app.models.plan import MealPlanItem
from app.models.profile import AvoidedFood
from app.models.user import User
from app.nutrition_core.conditions import POTASSIUM_SPARING_DRUGS
from app.planner import rules
from app.planner import service as planner
from app.profiles import service as profiles
from app.reports import summary
from app.targets import service as targets

WEEK_DAYS = 7
WEEKDAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")

# Fewer tracked days than this say too little about how someone eats to steer
# the whole of the next week's plan.
EMPHASIS_MIN_TRACKED_DAYS = 3


class NoProfile(LookupError):
    """No profile, so no targets to report against."""


@dataclass(frozen=True)
class ReportDayView:
    date: datetime.date
    weekday: str  # "Sun" .. "Sat"
    # tracked | untracked | in-progress | future. Only a tracked day counts in
    # any total.
    state: str
    energy_kcal: float
    # The day's base energy target, before any carry, at the recalibration in
    # force on that day.
    target_kcal: float


@dataclass(frozen=True)
class SuggestionView:
    nutrient_code: str
    display_name: str
    text: str
    foods: list[tuple[uuid.UUID, str]]


@dataclass(frozen=True)
class WeekReport:
    start_date: datetime.date
    end_date: datetime.date
    status: str  # complete | in-progress
    tracked_days: int
    slots_logged: int
    slots_skipped: int
    slots_expected: int
    measured_kcal: float
    estimated_kcal: float
    # Both None when the week has no plan at all.
    plan_planned: int | None
    plan_followed: int | None
    days: list[ReportDayView]
    nutrients: list[summary.NutrientWeek]
    uncompensated: list[summary.Gap]
    suggestions: list[SuggestionView]


@dataclass(frozen=True)
class _Week:
    """What the walk and the diary say about a week, before any dish is looked up."""

    context: targets.TargetContext
    elapsed: list[datetime.date]
    days: list[ReportDayView]
    breakdowns: list[diary.DayBreakdown]  # one per tracked day
    nutrients: list[summary.NutrientWeek]
    uncompensated: list[summary.Gap]
    excluded: frozenset[str]  # never suggested

    @property
    def tracked_days(self) -> int:
        return len(self.breakdowns)


def build_week(
    db: Session, user: User, week_start: datetime.date, today: datetime.date
) -> WeekReport:
    """One week's account, as of the user's `today`.

    Raises NoProfile without a profile. Raises ValueError for a week that does
    not start on a Sunday or has not started yet; the router refuses both
    first.
    """
    week = _gather(db, user, week_start, today)
    chosen = summary.nutrients_to_suggest(week.nutrients, week.tracked_days, week.excluded)
    logged, skipped, expected = _slot_counts(db, user, week.elapsed)
    planned, followed = _plan_adherence(db, user, week_start, week.elapsed)
    end_date = week_start + datetime.timedelta(days=WEEK_DAYS - 1)

    return WeekReport(
        start_date=week_start,
        end_date=end_date,
        # Complete once the Saturday has ended where the user is.
        status="complete" if end_date < today else "in-progress",
        tracked_days=week.tracked_days,
        slots_logged=logged,
        slots_skipped=skipped,
        slots_expected=expected,
        measured_kcal=sum(
            b.consumed.get("energy", 0.0) - b.estimated_energy for b in week.breakdowns
        ),
        estimated_kcal=sum(b.estimated_energy for b in week.breakdowns),
        plan_planned=planned,
        plan_followed=followed,
        days=week.days,
        nutrients=week.nutrients,
        uncompensated=week.uncompensated,
        suggestions=_suggestions(db, user, week.context, chosen) if chosen else [],
    )


def suggested_codes(
    db: Session, user: User, week_start: datetime.date, today: datetime.date
) -> list[str]:
    """The nutrients `build_week` would suggest for a week, for the next plan.

    Empty when the week has not started, or had fewer than three tracked days.
    It skips the dish lookup, which the planner does not need. Raises NoProfile
    like `build_week`; `generate_week` has checked the profile before it asks.
    """
    if week_start > today:
        return []
    week = _gather(db, user, week_start, today)
    if week.tracked_days < EMPHASIS_MIN_TRACKED_DAYS:
        return []
    chosen = summary.nutrients_to_suggest(week.nutrients, week.tracked_days, week.excluded)
    return [nutrient.code for nutrient in chosen]


def _gather(
    db: Session, user: User, week_start: datetime.date, today: datetime.date
) -> _Week:
    if rules.sunday_index(week_start) != 0:
        raise ValueError("a report week starts on a Sunday")
    if week_start > today:
        raise ValueError("a week that has not started has nothing to report")

    context = targets.load_context(db, user, week_start)
    if context is None:
        raise NoProfile

    week_end = week_start + datetime.timedelta(days=WEEK_DAYS - 1)
    # Today's clean slate, four days back. What the days before Sunday carried
    # into the week counts; older chains are not followed, which is a recorded gap.
    ledger = targets.walk_ledger(
        db,
        user,
        context,
        start=week_start - datetime.timedelta(days=targets.COMPENSATION_WINDOW_DAYS),
        end=min(week_end, today - datetime.timedelta(days=1)),
        as_of=today,
    )
    ears = {code: target.ear for code, target in context.overlay.targets.items()}
    limits = {code: target.tul for code, target in context.overlay.targets.items()}

    elapsed: list[datetime.date] = []
    days: list[ReportDayView] = []
    facts: list[summary.DayFacts] = []
    breakdowns: list[diary.DayBreakdown] = []
    for offset in range(WEEK_DAYS):
        day = week_start + datetime.timedelta(days=offset)
        if day >= today:
            # Not over yet, so outside the walk and counted in no total. Its
            # energy stays at zero, so a day still being eaten is not drawn as a
            # shortfall.
            state, energy = ("in-progress" if day == today else "future"), 0.0
            target = targets.base_targets_on(db, user, context, day)["energy"]
        else:
            elapsed.append(day)
            ledger_day = ledger.days[day]
            target = ledger_day.base["energy"]
            state, energy = "untracked", 0.0
            if ledger_day.tracked:
                state, energy = "tracked", ledger_day.consumed.get("energy", 0.0)
                breakdown = diary.day_breakdown(db, user, day)
                breakdowns.append(breakdown)
                facts.append(
                    summary.DayFacts(
                        date=day,
                        consumed=ledger_day.consumed,
                        coverage=breakdown.coverage,
                        base=ledger_day.base,
                        ear=ears,
                        effective=ledger_day.effective,
                        tul=limits,
                        expired_shortfall=ledger_day.expired_shortfall,
                    )
                )
        days.append(
            ReportDayView(
                date=day,
                weekday=WEEKDAY_NAMES[offset],
                state=state,
                energy_kcal=energy,
                target_kcal=target,
            )
        )

    meta = _meta(context)
    return _Week(
        context=context,
        elapsed=elapsed,
        days=days,
        breakdowns=breakdowns,
        nutrients=summary.summarise(facts, meta),
        uncompensated=summary.uncompensated(facts, meta, context.overlay.compensation_disabled),
        excluded=_excluded(db, user, context),
    )


def _meta(context: targets.TargetContext) -> dict[str, summary.NutrientMeta]:
    """Per nutrient, what the summary needs to name it and to explain its gaps.

    Compensability is the nutrients table's own flag, whether the body has a
    store to draw on. A nutrient held steady differs from it only in the policy,
    and `uncompensated` leaves those out anyway.
    """
    meta = {}
    for code, target in context.overlay.targets.items():
        row = context.nutrients.get(code)
        meta[code] = summary.NutrientMeta(
            code=code,
            # The fallbacks Today uses for a code the table lacks.
            display_name=row.display_name if row else code,
            unit=row.unit if row else "g",
            category=row.category if row else "macro",
            kind=target.kind,
            is_compensable=bool(row and row.is_compensable),
            carry_cap_fraction=context.policies[code].carry_cap_fraction,
        )
    return meta


def _excluded(db: Session, user: User, context: targets.TargetContext) -> frozenset[str]:
    """Never suggested: anything held steady, and potassium on a drug that raises it.

    Vitamin K on an anticoagulant is held steady, so the first rule covers it.
    Potassium is left out on any potassium-sparing drug, whether or not the user
    has the hypertension that would otherwise call for more (spec manual step 7b).
    """
    excluded = set(context.overlay.compensation_disabled)
    taken = [item.name.lower() for item in profiles.get_medications(db, user)]
    if any(drug in name for name in taken for drug in POTASSIUM_SPARING_DRUGS):
        excluded.add("potassium")
    return frozenset(excluded)


def _slot_counts(
    db: Session, user: User, elapsed: list[datetime.date]
) -> tuple[int, int, int]:
    """(logged, skipped, expected) over the days that have ended.

    Expected means the slots enabled now, on every elapsed day. That includes an
    untracked day, whose empty slots were missed. Food in a slot switched off
    since then is still food, but that slot was not expected, so it is not
    counted here.
    """
    disabled = {item.slot for item in profiles.get_meal_times(db, user) if not item.is_enabled}
    enabled = [slot for slot in SLOTS if slot not in disabled]
    logged = skipped = 0
    for day in elapsed:
        states = diary.slot_states(db, user, day)
        logged += sum(1 for slot in enabled if states.get(slot) == "logged")
        skipped += sum(1 for slot in enabled if states.get(slot) == "skipped")
    return logged, skipped, len(enabled) * len(elapsed)


def _plan_adherence(
    db: Session, user: User, week_start: datetime.date, elapsed: list[datetime.date]
) -> tuple[int | None, int | None]:
    """(planned, followed), counted over the days that have ended.

    Followed means the slot was logged with the planned dish that day. Both are
    None when the week has no plan.
    """
    plan = planner.get_plan(db, user, week_start)
    if plan is None:
        return None, None
    if not elapsed:
        return 0, 0

    items = db.scalars(
        select(MealPlanItem).where(
            MealPlanItem.plan_id == plan.id, MealPlanItem.plan_date.in_(elapsed)
        )
    ).all()
    eaten = {
        (logged_on, slot, dish_id)
        for logged_on, slot, dish_id in db.execute(
            select(MealLog.logged_on, MealLog.slot, MealLog.dish_id).where(
                MealLog.user_id == user.id,
                MealLog.logged_on.in_(elapsed),
                MealLog.dish_id.is_not(None),
            )
        )
    }
    followed = sum(1 for item in items if (item.plan_date, item.slot, item.dish_id) in eaten)
    return len(items), followed


def _suggestions(
    db: Session,
    user: User,
    context: targets.TargetContext,
    chosen: list[summary.NutrientWeek],
) -> list[SuggestionView]:
    """Dishes for each chosen nutrient, from the pool the planner draws on.

    It uses the planner's pool, diet and avoided foods, so every dish suggested
    is one the next plan could serve.
    """
    pool = planner.load_pool(db, user)
    avoided = tuple(
        rules.FoodRef(label=row.label, food_id=row.food_id, food_kind=row.food_kind)
        for row in profiles.get_preferences(db, user, AvoidedFood)
    )
    views = []
    for week in chosen:
        foods = summary.foods_for(week.code, pool, context.profile.diet_type, avoided)
        views.append(
            SuggestionView(
                nutrient_code=week.code,
                display_name=week.display_name,
                text=summary.suggestion_text(week, foods),
                foods=[(food.dish_id, food.name) for food in foods],
            )
        )
    return views


@dataclass(frozen=True)
class ProgressCounts:
    """A member's week as their household may see it: counts of days, and nothing else."""

    tracked_days: int
    # One nutrient-day per nutrient measured on each tracked day; met by the same
    # test as the report's days-met column.
    nutrient_days_met: int
    nutrient_days_measured: int


def member_progress(
    db: Session, member: User, week_start: datetime.date, today: datetime.date
) -> ProgressCounts | None:
    """A member's week as counts for their household. None when they have no profile.

    The counts are the member's own report, summed over the targets a profile has
    before any condition. Only the sums leave here: which nutrient fell short, and
    against what target, stays with the member, because a 1,500 mg sodium cap says
    hypertension as plainly as the diagnosis would. So does a target that only a
    condition creates, such as high cholesterol's cholesterol ceiling, or, from 60,
    hypertension's sodium and potassium. Counted, it would add one nutrient-day to
    every logged day.

    `today` is the member's own date. As in their report, only days that have
    ended are counted.
    """
    if profiles.get_profile(db, member) is None:
        return None
    if week_start > today:
        # A member in a timezone behind the viewer's may not have reached this
        # Sunday yet. None of the week has ended for them, so there is nothing to count.
        return ProgressCounts(tracked_days=0, nutrient_days_met=0, nutrient_days_measured=0)
    # The whole report, suggestions and all, for three sums. A household is a
    # handful of people and the screen asks once, and a single code path is what
    # keeps these counts the sums of the member's own report.
    report = build_week(db, member, week_start, today)
    # The codes `build_targets` gives before the overlay depend on sex and age band,
    # never on a condition or a drug, so counting only those keeps the counts silent
    # on both. A condition that moves a figure (sodium to 1,500 mg) is still counted:
    # it changes which days are met, never how many are measured.
    context = targets.load_context(db, member, week_start)
    public = set(context.built) if context is not None else set()
    counted = [week for week in report.nutrients if week.code in public]
    return ProgressCounts(
        tracked_days=report.tracked_days,
        nutrient_days_met=sum(week.days_met for week in counted),
        nutrient_days_measured=sum(week.measured_days for week in counted),
    )
