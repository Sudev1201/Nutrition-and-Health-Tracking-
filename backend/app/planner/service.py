"""Where the planner meets the database.

Three jobs: turn `dishes` into the engine's candidates, turn a profile and a
date into the engine's goals and constraints, and keep the stored plan in step
with what the engine decides. The engine itself never sees a Session.
"""

import datetime
import random
import uuid
import zoneinfo
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.diary import service as diary
from app.foods.measures import Measure, format_quantity, normalise_measure_name, resolve_grams
from app.foods.nutrition import (
    compute_dish_nutrients,
    compute_dish_nutrients_bulk,
    nutrients_for_portion,
)
from app.households import service as households
from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.food import Dish, DishIngredient, Ingredient, PortionMeasure
from app.models.plan import MealPlan, MealPlanItem
from app.models.profile import AvoidedFood, FavouriteIngredient, MealSlotTime, Profile
from app.models.user import User
from app.nutrition_core.conditions import EMPTY_STOMACH_DRUGS
from app.planner import engine, rules
from app.planner.engine import DayInput, NutrientGoal, PlannedItem
from app.planner.rules import Candidate, DayRules, FoodRef, Observance, Portion
from app.profiles import service as profiles
from app.targets import service as targets

# Multiples of a dish's default household measure the planner may suggest.
# "1½ dosa" is something people say; "0.37 dosa" is not, which is why portions
# are a ladder rather than a continuous scale.
PORTION_MULTIPLIERS = (1.0, 1.5, 2.0, 3.0)
# For a dish with no seeded measure of its own. Labelled in grams, honestly.
FALLBACK_GRAMS = (100.0, 150.0, 200.0)
WEEK_DAYS = 7


class NoProfile(LookupError):
    """Nothing can be planned before onboarding."""


class PlanItemNotFound(LookupError):
    pass


class ItemLocked(ValueError):
    pass


class NoAlternative(LookupError):
    """Every other dish the rules allow in this slot is already on the day."""


@dataclass(frozen=True)
class DayContext:
    """One day's constraints and goals, assembled from the profile and the diary."""

    date: datetime.date
    rules: DayRules
    vegetarian_reason: str | None
    goals: dict[str, NutrientGoal]
    hold_steady: frozenset[str]
    # slot -> earliest time to eat, when the slot falls inside the 60-minute window
    wait_until: dict[str, datetime.time] = field(default_factory=dict)
    disabled: frozenset[str] = frozenset()
    skipped: frozenset[str] = frozenset()
    logged: frozenset[str] = frozenset()
    # The dishes actually eaten today. `consumed` carries what they contributed;
    # this carries which they were, which is what stops one being suggested twice.
    eaten: frozenset[uuid.UUID] = frozenset()
    consumed: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemView:
    id: uuid.UUID
    slot: str
    dish_id: uuid.UUID
    dish_name: str
    portion: str
    locked: bool
    rationale: str | None


@dataclass(frozen=True)
class DayView:
    date: datetime.date
    weekday: str
    vegetarian: bool
    vegetarian_reason: str | None
    items: list[ItemView]


@dataclass(frozen=True)
class WeekView:
    start_date: datetime.date
    days: list[DayView]


@dataclass(frozen=True)
class Overlap:
    slot: str
    dish_name: str
    members: list[str]


# --- dates and portions ----------------------------------------------------------------


def week_start_for(day: datetime.date) -> datetime.date:
    """The Sunday on or before `day`."""
    return day - datetime.timedelta(days=rules.sunday_index(day))


def local_today(user: User) -> datetime.date:
    """Today where the user is. A day boundary is theirs, not the server's."""
    return datetime.datetime.now(zoneinfo.ZoneInfo(user.timezone)).date()


def portion_label(measure_name: str | None, quantity: float | None, grams: float) -> str:
    """The same composition the diary uses, so a plan item and a logged one read alike."""
    if measure_name is not None and quantity is not None:
        return f"{format_quantity(quantity)} {measure_name}"
    return f"{grams:g} g"


def portion_ladder(measures: Sequence[Measure]) -> tuple[Portion, ...]:
    """The portions the planner may suggest for a dish, ascending by weight.

    Built from the seeded default measure only. The other seeded measures ("2
    idli", "3 idli") are counts of the default and the ladder already reaches
    them; using them directly would label a portion "1 3 idli".
    """
    own = [m for m in measures if not m.is_approximate]
    if not own:
        return tuple(Portion(g, None, None, portion_label(None, None, g)) for g in FALLBACK_GRAMS)

    default = next((m for m in own if m.is_default), own[0])
    ladder: dict[int, Portion] = {}
    for quantity in PORTION_MULTIPLIERS:
        grams = resolve_grams(quantity, default.grams)
        ladder.setdefault(
            round(grams),
            Portion(grams, default.name, quantity, portion_label(default.name, quantity, grams)),
        )
    return tuple(sorted(ladder.values(), key=lambda p: p.grams))


# --- the dish pool ------------------------------------------------------------------------


def _visible_user_ids(db: Session, user: User) -> set[uuid.UUID]:
    """Whose dishes this user may be offered: their own, plus their household's."""
    ids = {user.id}
    household = households.get_household_for_user(db, user)
    if household is not None:
        ids |= {m.user_id for m in households.list_members(db, household.id)}
    return ids


def _slots_from_tags(slot_tags: str | None) -> frozenset[str]:
    tags = set((slot_tags or "").split())
    return frozenset(
        slot for slot in SLOTS if slot in tags or (slot.startswith("snack") and "snack" in tags)
    )


def _recipes_for(
    db: Session, dish_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """Every pool dish's ingredients, in one query, grouped in Python."""
    rows = db.execute(
        select(DishIngredient.dish_id, Ingredient.id, Ingredient.name)
        .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
        .where(DishIngredient.dish_id.in_(dish_ids))
        .order_by(Ingredient.name)
    ).all()

    recipes: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
    for dish_id, ingredient_id, name in rows:
        recipes.setdefault(dish_id, []).append((ingredient_id, name))
    return recipes


def _measures_for(db: Session, dish_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[Measure]]:
    """Every pool dish's own measures, in one query.

    `measures_for_food` appends the generic set ("1 cup" at 240 g and friends);
    those are approximate by construction and `portion_ladder` drops them, so
    the pool never needs them. Ordered so the ladder's fallback -- the first
    measure, when none is flagged default -- does not depend on the query plan.
    """
    rows = db.scalars(
        select(PortionMeasure)
        .where(PortionMeasure.dish_id.in_(dish_ids))
        .order_by(PortionMeasure.dish_id, PortionMeasure.is_default.desc(), PortionMeasure.grams)
    ).all()

    measures: dict[uuid.UUID, list[Measure]] = {}
    for row in rows:
        measures.setdefault(row.dish_id, []).append(
            Measure(
                name=normalise_measure_name(row.measure_name),
                grams=row.grams,
                is_default=row.is_default,
                is_approximate=False,
            )
        )
    return measures


def load_pool(db: Session, user: User) -> list[Candidate]:
    """Every dish the planner may consider, in a stable order.

    Only dishes with slot tags are plannable -- that is the authored set. INDB
    reference dishes carry no slots and no recipe, and are for logging what was
    eaten out rather than for suggesting what to cook.

    Loaded with a fixed number of queries rather than three per dish: this runs
    on every swap and on every off-plan log, and per-dish queries made that
    ~220 round trips over the seeded pool.
    """
    dishes = db.scalars(
        select(Dish)
        .where(
            Dish.slot_tags.is_not(None),
            or_(
                Dish.created_by_user_id.is_(None),
                Dish.created_by_user_id.in_(_visible_user_ids(db, user)),
            ),
        )
        .order_by(Dish.code)
    ).all()
    if not dishes:
        return []

    dish_ids = [dish.id for dish in dishes]
    recipes = _recipes_for(db, dish_ids)
    measures_by_dish = _measures_for(db, dish_ids)
    nutrients = compute_dish_nutrients_bulk(db, dish_ids)

    pool = []
    for dish in dishes:
        recipe = recipes.get(dish.id, [])
        measures = measures_by_dish.get(dish.id, [])
        portions = portion_ladder(measures)
        default = next((m for m in measures if m.is_default and not m.is_approximate), None)

        pool.append(
            Candidate(
                dish_id=dish.id,
                name=dish.name,
                slots=_slots_from_tags(dish.slot_tags),
                # An untagged dish is treated as non-vegetarian. Leaving it off a
                # vegetarian day is the mistake that costs nothing; the seed set
                # is fully tagged, so this only guards future user dishes.
                diet=dish.diet_tags or "nonveg",
                ingredient_ids=frozenset(row[0] for row in recipe),
                ingredient_names=tuple(row[1] for row in recipe),
                # A dish with no recipe carries fixed per-100g values instead,
                # which is one dish's worth of query rather than the pool's.
                per_100g=nutrients.get(dish.id) or compute_dish_nutrients(db, dish),
                portions=portions,
                default_grams=default.grams if default else portions[0].grams,
            )
        )
    return pool


# --- one day's context ----------------------------------------------------------------------


def _slot_time(item: MealSlotTime, day: datetime.date) -> datetime.time:
    weekend = rules.sunday_index(day) in (0, 6)
    return item.weekend_time if weekend and item.weekend_time else item.usual_time


def _default_time(slot: str) -> datetime.time:
    hour, minute = DEFAULT_SLOT_TIMES[slot].split(":")
    return datetime.time(int(hour), int(minute))


def _food_refs(db: Session, user: User, model) -> tuple[FoodRef, ...]:
    return tuple(
        FoodRef(label=row.label, food_id=row.food_id, food_kind=row.food_kind)
        for row in profiles.get_preferences(db, user, model)
    )


def build_context(db: Session, user: User, profile: Profile, day: datetime.date) -> DayContext:
    """Goals from the targets service, constraints from the profile, facts from the diary."""
    resolved = targets.resolve_day(db, user, day)
    if resolved is None:
        raise NoProfile
    goals = {
        n.code: NutrientGoal(n.code, n.display_name, n.target_effective, n.kind, n.tul)
        for n in resolved.nutrients
    }
    requirement = {
        n.code: n.rda for n in resolved.nutrients if n.code in rules.MINERAL_WINDOW_NUTRIENTS
    }

    observances = [
        Observance(
            kind=row.kind,
            label=row.label,
            weekday=row.weekday,
            start_date=row.start_date,
            end_date=row.end_date,
        )
        for row in profiles.get_observances(db, user)
    ]
    reason = rules.vegetarian_reason(day, observances)

    meal_times = profiles.get_meal_times(db, user)
    times = {slot: _default_time(slot) for slot in SLOTS}
    times.update({item.slot: _slot_time(item, day) for item in meal_times})

    doses = [
        item.taken_at
        for item in profiles.get_medications(db, user)
        if any(name in item.name.lower() for name in EMPTY_STOMACH_DRUGS)
    ]
    minutes_since: dict[str, int | None] = {}
    wait_until: dict[str, datetime.time] = {}
    for slot in SLOTS:
        gaps = [g for g in (rules.minutes_after(d, times[slot]) for d in doses) if g is not None]
        minutes_since[slot] = min(gaps) if gaps else None
        for dose in doses:
            wait = rules.wait_until(times[slot], dose)
            if wait is not None:
                wait_until[slot] = max(wait, wait_until.get(slot, wait))

    entries = diary.list_entries(db, user, day)

    return DayContext(
        date=day,
        rules=DayRules(
            vegetarian=reason is not None,
            profile_diet=profile.diet_type,
            avoided=_food_refs(db, user, AvoidedFood),
            minutes_since_dose=minutes_since,
            requirement=requirement,
        ),
        vegetarian_reason=reason,
        goals=goals,
        hold_steady=resolved.hold_steady,
        wait_until=wait_until,
        disabled=frozenset(item.slot for item in meal_times if not item.is_enabled),
        skipped=frozenset(diary.skipped_on(db, user, day)),
        logged=frozenset(entry.slot for entry in entries),
        eaten=frozenset(e.dish_id for e in entries if e.dish_id is not None),
        consumed=diary.consumed_on(db, user, day),
    )


# --- stored plans ------------------------------------------------------------------------------


def get_plan(db: Session, user: User, week_start: datetime.date) -> MealPlan | None:
    return db.scalar(
        select(MealPlan).where(MealPlan.user_id == user.id, MealPlan.week_start == week_start)
    )


def _items_for(db: Session, plan: MealPlan, day: datetime.date) -> list[MealPlanItem]:
    return list(
        db.scalars(
            select(MealPlanItem).where(
                MealPlanItem.plan_id == plan.id, MealPlanItem.plan_date == day
            )
        )
    )


def _planned_from_row(db: Session, row: MealPlanItem) -> PlannedItem:
    """A stored item as the engine sees it, so it can be held fixed and counted."""
    dish = db.get(Dish, row.dish_id)
    return PlannedItem(
        slot=row.slot,
        dish_id=row.dish_id,
        dish_name=dish.name,
        portion=Portion(
            row.grams,
            row.measure_name,
            row.quantity,
            portion_label(row.measure_name, row.quantity, row.grams),
        ),
        nutrients=nutrients_for_portion(db, dish, row.grams),
        rationale=row.rationale,
        locked=row.locked,
    )


def _with_wait_note(rationale: str | None, wait: datetime.time | None) -> str | None:
    if wait is None:
        return rationale
    note = f"Have this after {wait.strftime('%H:%M')} — 60 minutes clear of your levothyroxine"
    return f"{rationale}. {note}" if rationale else note


def _store(
    db: Session,
    plan: MealPlan,
    day: datetime.date,
    slots: Sequence[str],
    items: Sequence[PlannedItem],
    context: DayContext,
) -> None:
    """Replace the unlocked items in `slots` with `items`."""
    db.execute(
        delete(MealPlanItem).where(
            MealPlanItem.plan_id == plan.id,
            MealPlanItem.plan_date == day,
            MealPlanItem.locked.is_(False),
            MealPlanItem.slot.in_(list(slots)),
        )
    )
    db.flush()
    for item in items:
        db.add(
            MealPlanItem(
                plan_id=plan.id,
                plan_date=day,
                slot=item.slot,
                dish_id=item.dish_id,
                grams=item.portion.grams,
                measure_name=item.portion.measure_name,
                quantity=item.portion.quantity,
                locked=False,
                rationale=_with_wait_note(item.rationale, context.wait_until.get(item.slot)),
            )
        )
    db.flush()


def _new_seed() -> int:
    return random.SystemRandom().randrange(2**31)


def _day_input(
    context: DayContext,
    pool: Sequence[Candidate],
    open_slots: Sequence[str],
    fixed: Sequence[PlannedItem],
    favourites: tuple[FoodRef, ...],
) -> DayInput:
    return DayInput(
        date=context.date,
        goals=context.goals,
        slots={s: tuple(rules.candidates_for_slot(pool, s, context.rules)) for s in open_slots},
        fixed=tuple(fixed),
        consumed=context.consumed,
        favourites=favourites,
        hold_steady=context.hold_steady,
        # What was eaten today, so the engine does not serve it again today. A
        # soft exclusion, not a filter on the candidates: were it removed here, a
        # slot whose only candidate had been eaten would silently go unplanned
        # instead of falling back to it.
        eaten=context.eaten,
    )


def generate_week(
    db: Session, user: User, week_start: datetime.date, *, reseed: bool = False
) -> MealPlan:
    """Plan every open slot from today to Saturday, keeping locked items.

    Days that have already ended are left exactly as they are: you cannot plan
    yesterday. Slots that are logged, skipped or switched off are not planned,
    and what was logged counts toward the day so the plan covers the remainder.
    """
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile
    if rules.sunday_index(week_start) != 0:
        raise ValueError("a week starts on a Sunday")

    plan = get_plan(db, user, week_start)
    if plan is None:
        plan = MealPlan(user_id=user.id, week_start=week_start, seed=_new_seed())
        db.add(plan)
        db.flush()
    elif reseed:
        plan.seed = _new_seed()
        db.flush()

    rng = random.Random(plan.seed)
    pool = load_pool(db, user)
    favourites = _food_refs(db, user, FavouriteIngredient)
    today = local_today(user)

    history: Counter = Counter()
    yesterday: frozenset[uuid.UUID] = frozenset()
    inputs: list[DayInput] = []
    open_by_day: dict[datetime.date, list[str]] = {}
    contexts: dict[datetime.date, DayContext] = {}

    for offset in range(WEEK_DAYS):
        day = week_start + datetime.timedelta(days=offset)
        existing = _items_for(db, plan, day)
        if day < today:
            # Already eaten. Its dishes still count for variety.
            history.update(row.dish_id for row in existing)
            yesterday = frozenset(row.dish_id for row in existing)
            continue

        context = build_context(db, user, profile, day)
        # A locked item in a slot that has since been logged is not counted twice:
        # what was eaten is in `consumed`, and that is the fact that stands.
        fixed = [
            _planned_from_row(db, row)
            for row in existing
            if row.locked and row.slot not in context.logged
        ]
        closed = context.disabled | context.skipped | context.logged | {f.slot for f in fixed}
        open_slots = [slot for slot in SLOTS if slot not in closed]

        inputs.append(_day_input(context, pool, open_slots, fixed, favourites))
        open_by_day[day] = open_slots
        contexts[day] = context

    if inputs:
        first = inputs[0].date - datetime.timedelta(days=1)
        before = diary.consumed_on(db, user, first)
        if before:
            inputs[0] = replace(inputs[0], previous_day=before)

    for day_input, items in zip(inputs, engine.plan_week(inputs, rng, history, yesterday)):
        # Slots that are skipped or switched off lose any earlier suggestion too.
        stale = [
            slot
            for slot in SLOTS
            if slot in contexts[day_input.date].skipped | contexts[day_input.date].disabled
        ]
        _store(
            db, plan, day_input.date, [*open_by_day[day_input.date], *stale], items,
            contexts[day_input.date],
        )
    return plan


def replan_after_log(
    db: Session, user: User, day: datetime.date, slot: str, food_id: uuid.UUID
) -> bool:
    """Re-plan the slots after `slot` on `day`, if the log departs from the plan.

    Only that day, only the later unlocked slots, and only when the dish logged
    is not the one planned. Returns whether anything was re-planned.
    """
    plan = get_plan(db, user, week_start_for(day))
    if plan is None:
        return False
    # The same rule `generate_week` follows: a day that has already ended is never
    # planned, so back-dating a forgotten meal must not rewrite what that day held.
    if day < local_today(user):
        return False
    rows = _items_for(db, plan, day)
    planned = next((row for row in rows if row.slot == slot), None)
    if planned is not None and planned.dish_id == food_id:
        return False

    profile = profiles.get_profile(db, user)
    if profile is None:
        return False
    context = build_context(db, user, profile, day)

    later = SLOTS[SLOTS.index(slot) + 1 :]
    locked_slots = {row.slot for row in rows if row.locked}
    closed = context.disabled | context.skipped | context.logged | locked_slots
    open_slots = [s for s in later if s not in closed]
    if not open_slots:
        return False

    # Everything not being re-planned is held fixed: locked items, and the
    # earlier suggestions the user may still eat. Logged slots are represented
    # by `consumed`, so their planned items are left out rather than counted twice.
    fixed = [
        _planned_from_row(db, row)
        for row in rows
        if row.slot not in open_slots and row.slot not in context.logged
    ]
    pool = load_pool(db, user)
    favourites = _food_refs(db, user, FavouriteIngredient)
    day_input = _day_input(context, pool, open_slots, fixed, favourites)

    week_rows = db.scalars(select(MealPlanItem).where(MealPlanItem.plan_id == plan.id)).all()
    uses = Counter(row.dish_id for row in week_rows if row.plan_date != day)
    rng = random.Random(f"{plan.seed}:{day}:{slot}")

    items = engine.plan_day(day_input, rng, uses)
    _store(db, plan, day, open_slots, items, context)
    return True


def _owned_item(db: Session, user: User, item_id: uuid.UUID) -> tuple[MealPlanItem, MealPlan]:
    row = db.execute(
        select(MealPlanItem, MealPlan)
        .join(MealPlan, MealPlan.id == MealPlanItem.plan_id)
        .where(MealPlanItem.id == item_id, MealPlan.user_id == user.id)
    ).first()
    if row is None:
        raise PlanItemNotFound
    return row[0], row[1]


def set_locked(db: Session, user: User, item_id: uuid.UUID, locked: bool) -> MealPlan:
    item, plan = _owned_item(db, user, item_id)
    item.locked = locked
    db.flush()
    return plan


def swap_item(db: Session, user: User, item_id: uuid.UUID) -> MealPlan:
    """Replace one item with the best alternative that keeps the day feasible."""
    item, plan = _owned_item(db, user, item_id)
    if item.locked:
        raise ItemLocked
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile

    context = build_context(db, user, profile, item.plan_date)
    others = [
        _planned_from_row(db, row)
        for row in _items_for(db, plan, item.plan_date)
        if row.id != item.id and row.slot not in context.logged
    ]
    day_input = _day_input(
        context, load_pool(db, user), [item.slot], others,
        _food_refs(db, user, FavouriteIngredient),
    )
    rng = random.Random(f"{plan.seed}:{item.id}:{item.dish_id}")

    alternative = engine.alternative_for(
        day_input, item.slot, rng, exclude=frozenset({item.dish_id})
    )
    if alternative is None:
        raise NoAlternative

    item.dish_id = alternative.dish_id
    item.grams = alternative.portion.grams
    item.measure_name = alternative.portion.measure_name
    item.quantity = alternative.portion.quantity
    item.rationale = _with_wait_note(alternative.rationale, context.wait_until.get(item.slot))
    db.flush()
    return plan


# --- reading -------------------------------------------------------------------------------------


def describe_week(db: Session, user: User, plan: MealPlan) -> WeekView:
    observances = [
        Observance(
            kind=row.kind,
            label=row.label,
            weekday=row.weekday,
            start_date=row.start_date,
            end_date=row.end_date,
        )
        for row in profiles.get_observances(db, user)
    ]
    rows = db.execute(
        select(MealPlanItem, Dish)
        .join(Dish, Dish.id == MealPlanItem.dish_id)
        .where(MealPlanItem.plan_id == plan.id)
    ).all()
    order = {slot: index for index, slot in enumerate(SLOTS)}

    days = []
    for offset in range(WEEK_DAYS):
        day = plan.week_start + datetime.timedelta(days=offset)
        reason = rules.vegetarian_reason(day, observances)
        items = sorted(
            (
                ItemView(
                    id=item.id,
                    slot=item.slot,
                    dish_id=dish.id,
                    dish_name=dish.name,
                    portion=portion_label(item.measure_name, item.quantity, item.grams),
                    locked=item.locked,
                    rationale=item.rationale,
                )
                for item, dish in rows
                if item.plan_date == day
            ),
            key=lambda view: order[view.slot],
        )
        days.append(
            DayView(
                date=day,
                weekday=day.strftime("%A"),
                vegetarian=reason is not None,
                vegetarian_reason=reason,
                items=items,
            )
        )
    return WeekView(start_date=plan.week_start, days=days)


def cooking_view(db: Session, user: User, day: datetime.date) -> list[Overlap]:
    """Where household members' plans coincide on one day, so a dish is cooked once.

    Reads members who share progress -- the household default -- plus the user
    themselves. A plan is nutrition progress, not health data. Solo users get an
    empty list, since there is nothing to reconcile.
    """
    household = households.get_household_for_user(db, user)
    if household is None:
        return []
    visible = {
        member.user_id
        for member in households.list_members(db, household.id)
        if member.share_progress or member.user_id == user.id
    }
    rows = db.execute(
        select(MealPlanItem.slot, Dish.name, User.name)
        .join(MealPlan, MealPlan.id == MealPlanItem.plan_id)
        .join(Dish, Dish.id == MealPlanItem.dish_id)
        .join(User, User.id == MealPlan.user_id)
        .where(MealPlan.user_id.in_(visible), MealPlanItem.plan_date == day)
    ).all()

    groups: dict[tuple[str, str], list[str]] = {}
    for slot, dish_name, member_name in rows:
        groups.setdefault((slot, dish_name), []).append(member_name)

    order = {slot: index for index, slot in enumerate(SLOTS)}
    return [
        Overlap(slot=slot, dish_name=dish_name, members=sorted(members))
        for (slot, dish_name), members in sorted(groups.items(), key=lambda g: order[g[0][0]])
        if len(members) >= 2
    ]
