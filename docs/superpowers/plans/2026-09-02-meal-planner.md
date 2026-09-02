# Meal Planner Implementation Plan (plan 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real seven-day meal plan — generated from the user's own targets, observance rules, avoided foods and medication times, persisted, and editable by swap, lock and regenerate — replacing the last MSW fixture on the Plan screen.

**Architecture:** A pure planning engine (`app/planner/rules.py` for hard constraints, `app/planner/engine.py` for scoring, greedy construction, portion choice and local search) sits beside `nutrition_core` and never touches the database. `app/planner/service.py` feeds it: the dish pool from `dishes` (visibility: seed dishes plus the user's and their household's), the day's goals from `targets.service.resolve_day`, and the constraints from the profile. Plans persist in two new tables, `meal_plans` and `meal_plan_items`, keyed by user and week. `app/planner/router.py` implements the HTTP contract the frontend already calls (`frontend/src/plan/types.ts`).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest (backend); React 19, TanStack Query, MSW, Vitest, Playwright (frontend). No new dependencies — the spec's algorithm is greedy construction plus local search, which needs no solver.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md` — section "3. Meal planner", section "6. Diet observance rules", the medication table under the planner section, and "Solo Use & Households" (cooking view). The HTTP contract is `frontend/src/plan/types.ts` and the fixture `frontend/src/mocks/fixtures/plan.ts`.

**Status:** Complete. 377 backend tests and 197 frontend tests passing, plus 4
Playwright specs against a live API; `ruff`, `alembic check`, `oxlint`, `tsc -b`
and `vite build` all clean.

## Global Constraints

- Python `>=3.12`, `ruff` line length 100, `uv run` for every backend command, run from `backend/`.
- Every backend table extends `TimestampedBase` (UUID `id`, `created_at`), and every new model is registered in `app/models/__init__.py` — Alembic and the test fixtures read metadata from there.
- The test database runs against the **migrated** schema, never `create_all`. After adding a migration, run `DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head` **and** `uv run alembic upgrade head` (development database), or every test fails with a `UsageError` naming the fix.
- The full backend suite takes ~5 minutes. During a task run only the test files you touched (`uv run pytest tests/test_planner_engine.py -q`); the final task runs everything.
- Meal-slot vocabulary comes from `app.meal_slots.SLOTS` = `("breakfast", "snack1", "lunch", "snack2", "dinner")`. Never retype it.
- `dishes.slot_tags` is a space-separated subset of `{breakfast, snack, lunch, dinner}` — **`snack` covers both `snack1` and `snack2`**. `dishes.diet_tags` is one of `vegetarian | eggetarian | fishetarian | nonveg`. `profiles.diet_type` is one of `vegetarian | eggetarian | fishetarian | non-vegetarian` (note the hyphen; this vocabulary is fixed by `frontend/src/onboarding/types.ts`).
- `observance_rules.weekday` is **0 = Sunday**. Python's `date.weekday()` is 0 = Monday. Convert with `(day.weekday() + 1) % 7`.
- Frontend: `npx tsc -b` (never `--noEmit` alone), `npx vitest run`, `npm run lint` (oxlint), `npm run build`. Tests stub real endpoints per test with `server.use(...)`; unhandled requests fail the test.
- Code blocks in this plan are written for reading; wrap any line over 100 columns before committing (ruff `E501` will name them). Do not add `noqa`.
- Commit after each task. Messages follow the repo's style: a conventional prefix (`feat(backend):`, `feat(frontend):`, `test:`, `docs:`), a body that explains the *why*, and the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit on the current branch `tracking-loop-and-ui-foundation`; do not push.

## Decisions taken before starting

Recorded here so the implementer does not re-litigate them; the closeout document will carry them forward.

- **Generated on demand, not on Saturday evening.** `GET /plan/week` builds and stores the plan the first time a week is asked for. A scheduled Saturday run needs the job runner that plan 8 (reminders) introduces; until then, on-demand is the same plan a day later.
- **The planner never plans a day that has already ended** in the user's timezone (`users.timezone`, default `Asia/Kolkata`). You cannot plan yesterday. A first plan generated mid-week leaves the earlier days empty, and a regenerate leaves them untouched.
- **Goals are the ledger-adjusted `target_effective`, per day**, from `resolve_day`. That is the point of the tracking loop: a calcium shortfall yesterday raises what the planner aims for today. Future days simply have no carries and resolve to the published RDA.
- **One item per slot.** The spec's "paired beverage" for snacks needs a beverage tag the seed data does not carry; deferred and recorded as a gap. The schema has a unique key on `(plan_id, plan_date, slot)` so the contract's `items: PlanItem[]` still holds.
- **Food already logged is fixed, and the rest of the day is planned around it.** A logged slot is not re-planned; its nutrients count toward the day. This is also what makes intra-day re-planning one code path rather than two.
- **Logging a dish other than the planned one re-plans only the later slots of that day**, automatically, from `POST /diary/entries`. Locked items and the other six days are never touched. Logging the planned dish itself changes nothing.
- **Medication is a constraint, not a note.** Inside 4 h of a levothyroxine-class dose a slot refuses calcium- or iron-heavy dishes (one default portion carrying ≥ 10% of the day's requirement). Inside 60 min, the slot's item carries the earliest time to eat it. The potassium and warfarin rules are inherited from `apply_conditions` through the goals and a new `hold_steady` field, so the planner cannot disagree with the targets screen.
- **Portions are a ladder, not a continuum.** 1×, 1½×, 2× and 3× of the dish's seeded default measure, so a suggestion reads "3 idli" or "1½ cup", never "2.37 idli". The portion chosen is the rung whose energy is closest to the slot's share of what the day still needs.
- **Slot energy shares are named constants** (breakfast 25%, snacks 10% each, lunch 30%, dinner 25%), redistributed over the slots actually being planned. They are a dietetic convention for shaping a day, not a nutritional target; nothing scores against them.
- **The household cooking view is built**, as an endpoint and a card on the Plan screen shown only to household members. It reads only members who share progress (the household's default), since a plan is nutrition progress rather than health data.

---

## File structure

**Backend — create**

| File | Responsibility |
|---|---|
| `app/planner/__init__.py` | Package marker |
| `app/planner/rules.py` | Hard constraints, pure: diet class vs. observance day, avoided foods, favourite matches, medication windows, `candidates_for_slot` |
| `app/planner/engine.py` | Scoring and search, pure: weighted gap, portion choice, greedy day, local search, week loop, swap alternative, rationale text |
| `app/planner/service.py` | Database layer: dish pool, per-day context, generate / regenerate / re-plan / swap / lock, week view, cooking view |
| `app/planner/router.py` | The five endpoints of the contract |
| `app/models/plan.py` | `MealPlan`, `MealPlanItem` |
| `alembic/versions/d8e9f0a1b2c3_meal_plans.py` | The two tables |
| `tests/test_planner_rules.py`, `tests/test_planner_engine.py`, `tests/test_planner_api.py` | Pure-rule tests, pure-engine tests, and end-to-end API tests on a small seeded pool |

**Backend — modify**

| File | Change |
|---|---|
| `app/models/__init__.py` | Register the two models |
| `app/targets/service.py` | `DayTargets.hold_steady` — the overlay's `compensation_disabled`, so the planner learns "warfarin: hold vitamin K steady" from the same place the ledger does |
| `app/diary/router.py` | After `add_entry`, call `planner.replan_after_log` |
| `app/main.py` | Include the planner router |

**Frontend — modify**

| File | Change |
|---|---|
| `src/plan/PlanScreen.tsx` | Drop `DemoDataBanner`; 404 → onboarding empty state; empty-day text; mount `CookingView` |
| `src/plan/CookingView.tsx` (create) | The household card |
| `src/plan/usePlan.ts` | `useCookingView(date, enabled)` |
| `src/plan/PlanScreen.test.tsx` | Stub `/plan/week`, `/households/me`, `/plan/cooking` per test; new cases |
| `src/mocks/handlers/index.ts` | Delete the five plan handlers |
| `src/mocks/fixtures/plan.ts` | Keep (tests import it); update the header comment |
| `e2e/plan.spec.ts` (create) | The plan page against the real backend |
| `README.md` | "Which screens are real" |

**Docs — modify**: `docs/superpowers/plans/README.md` (row 6), this file's status line.

---

## Task 1: `DayTargets.hold_steady`

The planner must not re-derive "this user is on warfarin" from drug names — that would be a second copy of the rule in `conditions.py`. The overlay already computes `compensation_disabled`; expose it.

**Files:**
- Modify: `app/targets/service.py` (the `DayTargets` dataclass and the `return` at the end of `resolve_day`)
- Test: `tests/test_tracking_api.py` is unaffected; add the test below to `tests/test_targets_service.py` (create)

**Interfaces:**
- Produces: `DayTargets.hold_steady: frozenset[str]` — nutrient codes whose day-to-day variation must not be smoothed (`{"vitamin_k"}` on warfarin, otherwise empty).

- [ ] **Step 1: Write the failing test**

Create `tests/test_targets_service.py`:

```python
"""`resolve_day` exposes what the planner needs beyond the targets themselves."""

import datetime

from sqlalchemy import select

from app.models.user import User
from app.targets import service as targets
from tests.test_tracking_api import PROFILE

TODAY = datetime.date(2026, 8, 17)


def _user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


def test_warfarin_marks_vitamin_k_as_held_steady(signed_in, reference_data, db):
    signed_in.put(
        "/profile",
        json={**PROFILE, "medications": [{"name": "Warfarin", "time": "20:00"}]},
    )

    resolved = targets.resolve_day(db, _user(db), TODAY)

    assert resolved.hold_steady == frozenset({"vitamin_k"})


def test_nothing_is_held_steady_without_an_anticoagulant(signed_in, reference_data, db):
    signed_in.put("/profile", json=PROFILE)

    resolved = targets.resolve_day(db, _user(db), TODAY)

    assert resolved.hold_steady == frozenset()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_targets_service.py -q`
Expected: FAIL — `AttributeError: 'DayTargets' object has no attribute 'hold_steady'`

- [ ] **Step 3: Add the field**

In `app/targets/service.py`, extend the dataclass:

```python
@dataclass(frozen=True)
class DayTargets:
    date: datetime.date
    nutrients: list[NutrientDay]
    warnings: list[Warning]
    # Nutrients whose day-to-day variation must NOT be smoothed -- vitamin K on
    # warfarin. The ledger already honours this through `_policies`; the planner
    # reads it here so "hold steady" is decided in one place.
    hold_steady: frozenset[str] = frozenset()
```

and change the final `return` of `resolve_day` to:

```python
    return DayTargets(
        date=target_date,
        nutrients=rows,
        warnings=overlay.warnings,
        hold_steady=overlay.compensation_disabled,
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_targets_service.py tests/test_tracking_api.py -q`
Expected: all PASS (the router builds `TargetsOut` field by field, so the new attribute is invisible over HTTP).

- [ ] **Step 5: Commit**

```bash
git add app/targets/service.py tests/test_targets_service.py
git commit -m "feat(backend): expose which nutrients the overlay holds steady

The planner needs to know that a user on warfarin wants vitamin K level from
day to day. conditions.py already decides that as compensation_disabled; this
surfaces it on DayTargets rather than letting a second module match drug names.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: Planner rules (pure)

**Files:**
- Create: `app/planner/__init__.py` (empty), `app/planner/rules.py`
- Test: `tests/test_planner_rules.py`

**Interfaces (produced, used by every later task):**

```python
Portion(grams: float, measure_name: str | None, quantity: float | None, label: str)
Candidate(dish_id: uuid.UUID, name: str, slots: frozenset[str], diet: str,
          ingredient_ids: frozenset[uuid.UUID], ingredient_names: tuple[str, ...],
          per_100g: dict[str, float], portions: tuple[Portion, ...], default_grams: float)
FoodRef(label: str, food_id: uuid.UUID | None = None, food_kind: str | None = None)
Observance(kind: str, label: str = "", weekday: int | None = None,
           start_date: datetime.date | None = None, end_date: datetime.date | None = None)
DayRules(vegetarian: bool, profile_diet: str, avoided: tuple[FoodRef, ...] = (),
         minutes_since_dose: dict[str, int | None] = {}, requirement: dict[str, float] = {})

nutrients_for(candidate, grams) -> dict[str, float]
sunday_index(day) -> int
vegetarian_reason(day, rules: Sequence[Observance]) -> str | None
allowed_by_diet(candidate, rules: DayRules) -> bool
is_avoided(candidate, avoided: Sequence[FoodRef]) -> bool
favourite_hits(candidate, favourites: Sequence[FoodRef]) -> tuple[str, ...]
minutes_after(dose: datetime.time, slot_time: datetime.time) -> int | None
wait_until(slot_time: datetime.time, dose: datetime.time) -> datetime.time | None
is_mineral_heavy(candidate, rules: DayRules) -> bool
candidates_for_slot(pool: Sequence[Candidate], slot: str, rules: DayRules) -> list[Candidate]
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_planner_rules.py`:

```python
"""The planner's hard constraints, as pure functions.

Every rule here is one the spec calls a constraint rather than a preference: an
observance day, an avoided food, a medication window. A dish that fails one is
never scored, so the engine cannot trade it back in.
"""

import datetime
import uuid

from app.planner.rules import (
    Candidate,
    DayRules,
    FoodRef,
    Observance,
    Portion,
    candidates_for_slot,
    favourite_hits,
    is_avoided,
    is_mineral_heavy,
    minutes_after,
    sunday_index,
    vegetarian_reason,
    wait_until,
)

FRIDAY = datetime.date(2026, 8, 21)
SUNDAY = datetime.date(2026, 8, 16)

CURD_ID = uuid.uuid4()
RICE_ID = uuid.uuid4()


def candidate(
    name: str,
    slots: set[str],
    diet: str = "vegetarian",
    ingredients: tuple[tuple[uuid.UUID, str], ...] = ((RICE_ID, "Rice, raw, milled"),),
    per_100g: dict[str, float] | None = None,
    default_grams: float = 200.0,
) -> Candidate:
    return Candidate(
        dish_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset(slots),
        diet=diet,
        ingredient_ids=frozenset(i for i, _ in ingredients),
        ingredient_names=tuple(n for _, n in ingredients),
        per_100g=per_100g or {"energy": 130.0, "protein": 3.0, "calcium": 10.0},
        portions=(Portion(default_grams, "cup", 1.0, "1 cup"),),
        default_grams=default_grams,
    )


IDLI = candidate("Idli", {"breakfast", "snack1", "snack2", "dinner"})
SAMBAR_RICE = candidate("Rice with sambar", {"lunch", "dinner"})
CURD_RICE = candidate(
    "Curd rice",
    {"lunch", "dinner"},
    ingredients=((RICE_ID, "Rice, raw, milled"), (CURD_ID, "Curd, cow milk")),
    per_100g={"energy": 120.0, "protein": 4.0, "calcium": 65.0},
)
EGG_CURRY = candidate("Egg curry", {"lunch", "dinner"}, diet="eggetarian")
FISH_CURRY = candidate("Fish curry", {"lunch", "dinner"}, diet="fishetarian")
CHICKEN_CURRY = candidate("Chicken curry", {"lunch", "dinner"}, diet="nonveg")
POOL = [IDLI, SAMBAR_RICE, CURD_RICE, EGG_CURRY, FISH_CURRY, CHICKEN_CURRY]


def names(candidates) -> set[str]:
    return {c.name for c in candidates}


def rules(**overrides) -> DayRules:
    base = {"vegetarian": False, "profile_diet": "non-vegetarian"}
    return DayRules(**{**base, **overrides})


# --- observance days -----------------------------------------------------------


def test_the_weekday_index_counts_from_sunday():
    assert sunday_index(SUNDAY) == 0
    assert sunday_index(FRIDAY) == 5


def test_a_weekday_rule_names_the_day_when_it_has_no_label():
    friday_rule = Observance(kind="weekday", weekday=5)

    assert vegetarian_reason(FRIDAY, [friday_rule]) == "your Friday rule"
    assert vegetarian_reason(SUNDAY, [friday_rule]) is None


def test_a_labelled_rule_is_explained_by_its_label():
    purattasi = Observance(
        kind="date_range",
        label="Purattasi",
        start_date=datetime.date(2026, 9, 17),
        end_date=datetime.date(2026, 10, 17),
    )

    assert vegetarian_reason(datetime.date(2026, 10, 17), [purattasi]) == "Purattasi"
    assert vegetarian_reason(datetime.date(2026, 10, 18), [purattasi]) is None


def test_a_single_date_rule_matches_only_that_date():
    festival = Observance(kind="single_date", label="Vinayaka Chaturthi", start_date=FRIDAY)

    assert vegetarian_reason(FRIDAY, [festival]) == "Vinayaka Chaturthi"
    assert vegetarian_reason(FRIDAY + datetime.timedelta(days=1), [festival]) is None


# On an observance day egg counts as non-vegetarian and goes with meat and fish.
def test_a_vegetarian_day_excludes_egg_fish_and_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(vegetarian=True))

    assert names(allowed) == {"Rice with sambar", "Curd rice"}


# --- the standing diet -----------------------------------------------------------


def test_an_eggetarian_gets_egg_but_not_fish_or_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(profile_diet="eggetarian"))

    assert names(allowed) == {"Rice with sambar", "Curd rice", "Egg curry"}


def test_a_fishetarian_gets_fish_and_egg_but_not_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(profile_diet="fishetarian"))

    assert "Fish curry" in names(allowed)
    assert "Egg curry" in names(allowed)
    assert "Chicken curry" not in names(allowed)


def test_a_non_vegetarian_gets_everything_on_an_ordinary_day():
    allowed = candidates_for_slot(POOL, "lunch", rules())

    assert names(allowed) == {
        "Rice with sambar", "Curd rice", "Egg curry", "Fish curry", "Chicken curry",
    }


def test_a_dish_is_only_offered_in_its_own_slots():
    assert "Idli" not in names(candidates_for_slot(POOL, "lunch", rules()))
    assert "Idli" in names(candidates_for_slot(POOL, "breakfast", rules()))


# --- avoided and favourite foods -------------------------------------------------


def test_an_avoided_dish_is_blocked_by_id():
    assert is_avoided(CURD_RICE, [FoodRef("Curd rice", CURD_RICE.dish_id, "dish")])
    assert not is_avoided(SAMBAR_RICE, [FoodRef("Curd rice", CURD_RICE.dish_id, "dish")])


def test_an_avoided_ingredient_blocks_every_dish_containing_it():
    avoided = [FoodRef("Curd", CURD_ID, "ingredient")]

    assert is_avoided(CURD_RICE, avoided)
    assert not is_avoided(SAMBAR_RICE, avoided)


def test_free_text_avoidance_matches_names_case_insensitively():
    assert is_avoided(CURD_RICE, [FoodRef("curd")])
    assert is_avoided(CURD_RICE, [FoodRef("CURD RICE")])
    assert not is_avoided(SAMBAR_RICE, [FoodRef("curd")])
    assert not is_avoided(SAMBAR_RICE, [FoodRef("   ")])


def test_favourites_are_reported_by_label():
    favourites = [FoodRef("Curd", CURD_ID, "ingredient"), FoodRef("idli")]

    assert favourite_hits(CURD_RICE, favourites) == ("Curd",)
    assert favourite_hits(IDLI, favourites) == ("idli",)
    assert favourite_hits(SAMBAR_RICE, favourites) == ()


# --- medication windows ----------------------------------------------------------


def test_minutes_after_a_dose_is_none_when_the_slot_comes_first():
    assert minutes_after(datetime.time(7, 0), datetime.time(8, 0)) == 60
    assert minutes_after(datetime.time(22, 0), datetime.time(20, 30)) is None


def test_the_sixty_minute_wait_is_reported_as_a_clock_time():
    assert wait_until(datetime.time(7, 30), datetime.time(7, 0)) == datetime.time(8, 0)
    assert wait_until(datetime.time(8, 0), datetime.time(7, 0)) is None
    assert wait_until(datetime.time(6, 0), datetime.time(7, 0)) is None


def test_a_dish_is_mineral_heavy_at_a_tenth_of_the_days_requirement():
    requirement = {"calcium": 1000.0}

    # 200 g of curd rice at 65 mg/100 g = 130 mg, over the 100 mg line.
    assert is_mineral_heavy(CURD_RICE, rules(requirement=requirement))
    # 200 g of sambar rice at 10 mg/100 g = 20 mg.
    assert not is_mineral_heavy(SAMBAR_RICE, rules(requirement=requirement))


def test_calcium_heavy_dishes_are_refused_inside_four_hours_of_the_dose():
    inside = rules(minutes_since_dose={"lunch": 180}, requirement={"calcium": 1000.0})
    clear = rules(minutes_since_dose={"lunch": 300}, requirement={"calcium": 1000.0})
    before = rules(minutes_since_dose={"lunch": None}, requirement={"calcium": 1000.0})

    assert "Curd rice" not in names(candidates_for_slot(POOL, "lunch", inside))
    assert "Rice with sambar" in names(candidates_for_slot(POOL, "lunch", inside))
    assert "Curd rice" in names(candidates_for_slot(POOL, "lunch", clear))
    assert "Curd rice" in names(candidates_for_slot(POOL, "lunch", before))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_planner_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.planner'`

- [ ] **Step 3: Implement the rules**

Create `app/planner/__init__.py` (empty) and `app/planner/rules.py`:

```python
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
DISH_DIET_RANK = {"vegetarian": 0, "eggetarian": 1, "fishetarian": 2, "nonveg": 3}
PROFILE_DIET_RANK = {"vegetarian": 0, "eggetarian": 1, "fishetarian": 2, "non-vegetarian": 3}

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
    return {code: value * grams / 100.0 for code, value in candidate.per_100g.items()}


def sunday_index(day: datetime.date) -> int:
    """0 = Sunday, matching `observance_rules.weekday`. Python's weekday() has Monday = 0."""
    return (day.weekday() + 1) % 7


def vegetarian_reason(day: datetime.date, rules: Sequence[Observance]) -> str | None:
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


def favourite_hits(candidate: Candidate, favourites: Sequence[FoodRef]) -> tuple[str, ...]:
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
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_planner_rules.py -q && uv run ruff check app/planner tests/test_planner_rules.py`
Expected: all PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/planner/__init__.py app/planner/rules.py tests/test_planner_rules.py
git commit -m "feat(backend): add the planner's hard constraints as pure rules

Observance days (egg counts as non-vegetarian), the standing diet, avoided
foods by id or by name, and the levothyroxine windows. A dish that fails one is
never scored, so the engine cannot trade it back in for a better nutrient fit.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 3: Planner engine (pure)

**Files:**
- Create: `app/planner/engine.py`
- Test: `tests/test_planner_engine.py`

**Interfaces:**
- Consumes: `Candidate`, `Portion`, `FoodRef`, `favourite_hits`, `nutrients_for` from Task 2; `SLOTS` from `app.meal_slots`.
- Produces:

```python
NutrientGoal(code: str, display_name: str, amount: float, kind: str, tul: float | None = None)
PlannedItem(slot: str, dish_id: uuid.UUID, dish_name: str, portion: Portion,
            nutrients: dict[str, float], favourites: tuple[str, ...] = (),
            rationale: str | None = None, locked: bool = False)
DayInput(date: datetime.date, goals: dict[str, NutrientGoal],
         slots: dict[str, tuple[Candidate, ...]],            # slots to fill -> allowed dishes
         fixed: tuple[PlannedItem, ...] = (),                 # locked items, kept and counted
         consumed: dict[str, float] = {},                     # logged food, counted
         favourites: tuple[FoodRef, ...] = (),
         hold_steady: frozenset[str] = frozenset(),
         previous_day: dict[str, float] | None = None)        # yesterday's totals, for hold_steady

add_totals(*parts: dict[str, float]) -> dict[str, float]
weighted_gap(totals, goals) -> float
day_cost(totals, day) -> float
energy_budget(day, slot, placed_totals, open_slots) -> float
portion_for(candidate, budget) -> Portion
plan_day(day, rng, uses: Counter | None = None, yesterday: frozenset = frozenset()) -> list[PlannedItem]
plan_week(days: Sequence[DayInput], rng, history: Counter | None = None,
          yesterday: frozenset = frozenset()) -> list[list[PlannedItem]]
alternative_for(day, slot, rng, exclude: frozenset[uuid.UUID]) -> PlannedItem | None
explain(day, fixed_totals, items: dict[str, PlannedItem], slot) -> str | None
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_planner_engine.py`:

```python
"""The planner's construction and search, on a synthetic pool.

These pin the behaviours the spec asks for -- fills every slot, closes the
weighted gap, varies the week, honours locks, plans around what was eaten --
without any database. Numbers are chosen so each test has one obvious answer.
"""

import datetime
import random
import uuid
from collections import Counter

import pytest

from app.planner.engine import (
    DayInput,
    NutrientGoal,
    PlannedItem,
    add_totals,
    alternative_for,
    day_cost,
    energy_budget,
    plan_day,
    plan_week,
    portion_for,
    weighted_gap,
)
from app.planner.rules import Candidate, FoodRef, Portion

MONDAY = datetime.date(2026, 8, 17)


def candidate(
    name: str,
    slots: set[str],
    energy: float,
    protein: float = 0.0,
    calcium: float = 0.0,
    vitamin_k: float = 0.0,
    grams: tuple[float, ...] = (100.0, 150.0, 200.0, 300.0),
    ingredients: tuple[str, ...] = (),
) -> Candidate:
    return Candidate(
        dish_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset(slots),
        diet="vegetarian",
        ingredient_ids=frozenset(uuid.uuid5(uuid.NAMESPACE_DNS, i) for i in ingredients),
        ingredient_names=ingredients,
        per_100g={
            "energy": energy, "protein": protein, "calcium": calcium, "vitamin_k": vitamin_k,
        },
        portions=tuple(Portion(g, "cup", g / 100.0, f"{g / 100.0:g} cup") for g in grams),
        default_grams=grams[0],
    )


GOALS = {
    "energy": NutrientGoal("energy", "Energy", 2000.0, "target"),
    "protein": NutrientGoal("protein", "Protein", 60.0, "target"),
    "calcium": NutrientGoal("calcium", "Calcium", 1000.0, "target", tul=2500.0),
    "sodium": NutrientGoal("sodium", "Sodium", 2000.0, "ceiling"),
    "vitamin_k": NutrientGoal("vitamin_k", "Vitamin K", 55.0, "target"),
}

IDLI = candidate("Idli", {"breakfast", "dinner"}, energy=130, protein=4, calcium=10)
DAL_RICE = candidate("Dal rice", {"lunch", "dinner"}, energy=150, protein=6, calcium=20)
# Calcium is deliberately its standout: 300 g covers 27% of the calcium goal
# against 15% of protein, so the rationale test has one right answer.
CURD_RICE = candidate("Curd rice", {"lunch", "dinner"}, energy=120, protein=3, calcium=90)
KEERAI = candidate("Keerai rice", {"lunch", "dinner"}, energy=140, protein=5, vitamin_k=120)
SUNDAL = candidate("Sundal", {"snack1", "snack2"}, energy=160, protein=9, calcium=50)
COFFEE = candidate("Filter coffee", {"snack1", "snack2"}, energy=60, protein=3, calcium=120)

MAIN_POOL = (IDLI, DAL_RICE, CURD_RICE, KEERAI, SUNDAL, COFFEE)


def slots_from(pool, slots=("breakfast", "snack1", "lunch", "snack2", "dinner")):
    return {slot: tuple(c for c in pool if slot in c.slots) for slot in slots}


def day(**overrides) -> DayInput:
    base = {"date": MONDAY, "goals": GOALS, "slots": slots_from(MAIN_POOL)}
    return DayInput(**{**base, **overrides})


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- the cost function -----------------------------------------------------------


def test_a_target_below_its_goal_costs_and_above_it_costs_nothing():
    goals = {"protein": GOALS["protein"]}

    assert weighted_gap({"protein": 30.0}, goals) == pytest.approx(2.0 * 0.5)
    assert weighted_gap({"protein": 90.0}, goals) == 0.0


def test_a_ceiling_costs_only_when_exceeded():
    goals = {"sodium": GOALS["sodium"]}

    assert weighted_gap({"sodium": 1500.0}, goals) == 0.0
    assert weighted_gap({"sodium": 3000.0}, goals) > 0.0


def test_breaching_the_upper_limit_is_penalised_hard():
    goals = {"calcium": GOALS["calcium"]}

    assert weighted_gap({"calcium": 3000.0}, goals) > weighted_gap({"calcium": 0.0}, goals)


def test_holding_a_nutrient_steady_penalises_a_swing_from_yesterday():
    steady = day(hold_steady=frozenset({"vitamin_k"}), previous_day={"vitamin_k": 50.0})

    level = day_cost({"vitamin_k": 55.0}, steady)
    swung = day_cost({"vitamin_k": 150.0}, steady)

    assert swung > level


# --- portions ----------------------------------------------------------------------


def test_the_portion_closest_to_the_energy_budget_is_chosen():
    # Dal rice is 150 kcal/100 g: 200 g is 300 kcal, 300 g is 450 kcal.
    assert portion_for(DAL_RICE, 320.0).grams == 200.0
    assert portion_for(DAL_RICE, 420.0).grams == 300.0


def test_the_energy_budget_shares_what_is_left_over_the_open_slots():
    # 2000 kcal, nothing placed: lunch is 30% of the day.
    assert energy_budget(day(), "lunch", {}, ["breakfast", "snack1", "lunch", "snack2", "dinner"]) == pytest.approx(600.0)
    # 800 kcal already eaten and only lunch and dinner open: 1200 left, split 30:25.
    assert energy_budget(day(), "lunch", {"energy": 800.0}, ["lunch", "dinner"]) == pytest.approx(1200.0 * 30 / 55)


# --- one day -----------------------------------------------------------------------


def test_every_open_slot_is_filled_from_its_own_candidates():
    items = plan_day(day(), rng())

    assert [item.slot for item in items] == ["breakfast", "snack1", "lunch", "snack2", "dinner"]
    for item in items:
        allowed = {c.dish_id for c in day().slots[item.slot]}
        assert item.dish_id in allowed


def test_a_slot_with_no_candidates_is_left_empty_rather_than_invented():
    items = plan_day(day(slots={"lunch": (), "dinner": (DAL_RICE,)}), rng())

    assert [item.slot for item in items] == ["dinner"]


def test_the_same_seed_gives_the_same_plan():
    first = plan_day(day(), rng(7))
    second = plan_day(day(), rng(7))

    assert [(i.dish_id, i.portion.grams) for i in first] == [
        (i.dish_id, i.portion.grams) for i in second
    ]


def test_the_plan_beats_doing_nothing_and_never_repeats_a_dish_within_a_day():
    planned = plan_day(day(), rng())
    totals = add_totals(*(item.nutrients for item in planned))

    assert day_cost(totals, day()) < day_cost({}, day())
    assert len({item.dish_id for item in planned}) == len(planned)


def test_food_already_eaten_shrinks_what_is_planned():
    hungry = plan_day(day(), rng(3))
    fed = plan_day(day(consumed={"energy": 1200.0, "protein": 40.0}), rng(3))

    assert sum(i.nutrients["energy"] for i in fed) < sum(i.nutrients["energy"] for i in hungry)


def test_a_locked_item_is_kept_and_its_slot_is_not_planned_again():
    locked = PlannedItem(
        slot="lunch",
        dish_id=CURD_RICE.dish_id,
        dish_name="Curd rice",
        portion=CURD_RICE.portions[2],
        nutrients={"energy": 240.0, "protein": 8.0, "calcium": 130.0},
        locked=True,
    )
    open_slots = {s: c for s, c in slots_from(MAIN_POOL).items() if s != "lunch"}

    items = plan_day(day(slots=open_slots, fixed=(locked,)), rng())

    assert "lunch" not in {item.slot for item in items}
    assert CURD_RICE.dish_id not in {item.dish_id for item in items}


def test_the_rationale_names_the_nutrient_a_dish_does_most_for():
    # Curd rice is the only lunch dish carrying real calcium against a 1000 mg goal.
    items = plan_day(day(slots={"lunch": (CURD_RICE,)}), rng())

    assert items[0].rationale is not None
    assert "calcium" in items[0].rationale.lower()


def test_a_favourite_is_mentioned_when_a_dish_carries_it():
    with_curd = candidate("Curd rice", {"lunch"}, energy=120, ingredients=("Curd", "Rice"))
    items = plan_day(
        day(slots={"lunch": (with_curd,)}, favourites=(FoodRef("Curd"),)), rng()
    )

    assert items[0].favourites == ("Curd",)
    assert "curd" in (items[0].rationale or "").lower()


def test_no_rationale_is_invented_for_an_unremarkable_dish():
    plain = candidate("Plain rice", {"lunch"}, energy=130, grams=(50.0,))
    items = plan_day(day(slots={"lunch": (plain,)}), rng())

    assert items[0].rationale is None


# --- the week --------------------------------------------------------------------------


def test_a_week_does_not_serve_the_same_dinner_every_night():
    days = [day(date=MONDAY + datetime.timedelta(days=n)) for n in range(7)]

    week = plan_week(days, rng(11))
    dinners = [next(i.dish_id for i in items if i.slot == "dinner") for items in week]

    assert len(set(dinners)) > 1


def test_a_held_steady_nutrient_stays_level_across_the_week():
    # Keerai is the only source of vitamin K. With nothing held, the planner
    # reaches for it whenever calcium and protein allow; with warfarin, the
    # swing between consecutive days must stay inside the tolerance.
    days = [
        day(date=MONDAY + datetime.timedelta(days=n), hold_steady=frozenset({"vitamin_k"}))
        for n in range(4)
    ]

    week = plan_week(days, rng(5))
    vitamin_k = [sum(i.nutrients["vitamin_k"] for i in items) for items in week]

    swings = [abs(b - a) / GOALS["vitamin_k"].amount for a, b in zip(vitamin_k, vitamin_k[1:])]
    assert max(swings) <= 0.25 + 1e-9 or all(v == vitamin_k[0] for v in vitamin_k)


# --- swapping ------------------------------------------------------------------------


def test_the_alternative_for_a_slot_is_a_different_dish_that_fits():
    current = plan_day(day(), rng())
    lunch = next(i for i in current if i.slot == "lunch")
    others = tuple(i for i in current if i.slot != "lunch")

    swapped = alternative_for(
        day(slots={"lunch": slots_from(MAIN_POOL)["lunch"]}, fixed=others),
        "lunch",
        rng(2),
        exclude=frozenset({lunch.dish_id}),
    )

    assert swapped is not None
    assert swapped.slot == "lunch"
    assert swapped.dish_id != lunch.dish_id
    assert swapped.dish_id not in {i.dish_id for i in others}


def test_no_alternative_when_every_other_candidate_is_excluded():
    assert alternative_for(
        day(slots={"lunch": (DAL_RICE,)}), "lunch", rng(), exclude=frozenset({DAL_RICE.dish_id})
    ) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_planner_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.planner.engine'`

- [ ] **Step 3: Implement the engine**

Create `app/planner/engine.py`:

```python
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
SLOT_ENERGY_SHARE = {"breakfast": 0.25, "snack1": 0.10, "lunch": 0.30, "snack2": 0.10, "dinner": 0.25}

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
        used_today = fixed_dishes | frozenset(i.dish_id for i in items.values())
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
            exclude = fixed_dishes | frozenset(i.dish_id for i in others.values())
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
    used = exclude | frozenset(item.dish_id for item in day.fixed)
    chosen = _choose_for_slot(day, slot, fixed_totals, [slot], Counter(), frozenset(), rng, used)
    if chosen is None:
        return None
    items = {item.slot: item for item in day.fixed} | {slot: chosen}
    return replace(chosen, rationale=explain(day, day.consumed, items, slot))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_planner_engine.py tests/test_planner_rules.py -q && uv run ruff check app/planner tests/`
Expected: all PASS, ruff clean. If `test_a_held_steady_nutrient_stays_level_across_the_week` fails, the fix is in the constants, not the test: the swing penalty must be large enough that keerai on one day and none the next (120 mg × 100 g / 55 mg goal ≈ a 2.2 swing) costs more than the protein it adds.

- [ ] **Step 5: Commit**

```bash
git add app/planner/engine.py tests/test_planner_engine.py
git commit -m "feat(backend): add the planning engine -- weighted gap, greedy, local search

Pure and seeded. Scores each dish on how much of the day's weighted nutrient gap
it closes, sizes the portion to the slot's share of what the day still needs,
then swaps out whatever a better alternative exists for. Logged and locked food
is fixed and counted, which is what lets one code path plan a week and re-plan
the rest of an afternoon.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 4: Models and migration

**Files:**
- Create: `app/models/plan.py`, `alembic/versions/d8e9f0a1b2c3_meal_plans.py`
- Modify: `app/models/__init__.py`

**Interfaces (produced):**

```python
class MealPlan(TimestampedBase):      # meal_plans
    user_id: uuid.UUID; week_start: datetime.date; seed: int
class MealPlanItem(TimestampedBase):  # meal_plan_items
    plan_id: uuid.UUID; plan_date: datetime.date; slot: str; dish_id: uuid.UUID
    grams: float; measure_name: str | None; quantity: float | None
    locked: bool; rationale: str | None
```

- [ ] **Step 1: Write the models**

Create `app/models/plan.py`:

```python
import datetime
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class MealPlan(TimestampedBase):
    """One user's plan for one Sunday-to-Saturday week.

    The plan is per user even inside a household: targets, observances and
    medications are all personal, and the cooking view reconciles members' plans
    after the fact rather than the planner producing one shared menu.
    """

    __tablename__ = "meal_plans"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_plan_user_week"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Always a Sunday. The week runs Sunday to Saturday, per the spec.
    week_start: Mapped[datetime.date] = mapped_column(Date)
    # What the planner's random source was started with. Regenerating draws a new
    # one; keeping it means a plan can be reproduced exactly when a suggestion
    # needs explaining.
    seed: Mapped[int] = mapped_column(Integer)


class MealPlanItem(TimestampedBase):
    """One dish in one slot on one day of a plan.

    A quantity is two numbers here as it is in the diary: the household measure
    the user reads ("3 idli") and the grams the engine costed. Locked items
    survive regeneration and re-planning; everything else is disposable.
    """

    __tablename__ = "meal_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "plan_date", "slot", name="uq_plan_item_day_slot"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), index=True
    )
    plan_date: Mapped[datetime.date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(12))

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="RESTRICT"), index=True
    )
    grams: Mapped[float] = mapped_column(Float)
    measure_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)

    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Why the planner chose this, in the user's terms. Null when it had nothing
    # worth saying -- an empty reason is worse than none.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Register in `app/models/__init__.py`: add `from app.models.plan import MealPlan, MealPlanItem` (keep imports alphabetical by module: after `household`, before `nutrient`) and add `"MealPlan", "MealPlanItem"` to `__all__` in alphabetical position.

- [ ] **Step 2: Write the migration**

Create `alembic/versions/d8e9f0a1b2c3_meal_plans.py`:

```python
"""meal plans

Two tables. `meal_plans` is one user's Sunday-to-Saturday week, with the seed the
planner was started from so a plan can be reproduced when a suggestion needs
explaining. `meal_plan_items` is one dish per slot per day, carrying both the
household measure and the grams, as the diary does.

One item per slot is a deliberate limit: the unique key on (plan, date, slot) is
what makes swap and lock address a slot unambiguously. The spec's paired snack
beverage would relax it, and needs a beverage tag the seed data does not carry.

Revision ID: d8e9f0a1b2c3
Revises: c75ad3647c6b
Create Date: 2026-09-02

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | Sequence[str] | None = "c75ad3647c6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "meal_plans",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start", name="uq_plan_user_week"),
    )
    op.create_index(op.f("ix_meal_plans_user_id"), "meal_plans", ["user_id"], unique=False)

    op.create_table(
        "meal_plan_items",
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=12), nullable=False),
        sa.Column("dish_id", sa.UUID(), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.Column("measure_name", sa.String(length=40), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["meal_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "plan_date", "slot", name="uq_plan_item_day_slot"),
    )
    op.create_index(op.f("ix_meal_plan_items_dish_id"), "meal_plan_items", ["dish_id"], unique=False)
    op.create_index(op.f("ix_meal_plan_items_plan_date"), "meal_plan_items", ["plan_date"], unique=False)
    op.create_index(op.f("ix_meal_plan_items_plan_id"), "meal_plan_items", ["plan_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_meal_plan_items_plan_id"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_plan_date"), table_name="meal_plan_items")
    op.drop_index(op.f("ix_meal_plan_items_dish_id"), table_name="meal_plan_items")
    op.drop_table("meal_plan_items")
    op.drop_index(op.f("ix_meal_plans_user_id"), table_name="meal_plans")
    op.drop_table("meal_plans")
```

- [ ] **Step 3: Migrate both databases and check the migration matches the models**

```bash
uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head
uv run alembic check
```

Expected: both upgrades print `Running upgrade c75ad3647c6b -> d8e9f0a1b2c3, meal plans`; `alembic check` prints `No new upgrade operations detected.` If `alembic check` reports a difference, fix the **migration** to match the model (the model is the source of truth), then downgrade and re-upgrade both databases.

- [ ] **Step 4: Run the model tests and ruff**

Run: `uv run pytest tests/test_food_models.py tests/test_household_models.py -q && uv run ruff check app/models alembic/versions/d8e9f0a1b2c3_meal_plans.py`
Expected: PASS, ruff clean (the `E501` long index lines are fine at 100 columns; wrap them if ruff objects).

- [ ] **Step 5: Commit**

```bash
git add app/models/plan.py app/models/__init__.py alembic/versions/d8e9f0a1b2c3_meal_plans.py
git commit -m "feat(backend): add the meal_plans and meal_plan_items tables

One plan per user per Sunday-to-Saturday week, one dish per slot per day. The
seed is stored so a plan can be reproduced when a suggestion needs explaining,
and each item carries both the household measure and the grams, as the diary does.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 5: Planner service and router

The database layer, the five endpoints, and the diary hook. Tested end to end over HTTP on a small seeded pool, exactly as `test_tracking_api.py` tests the tracking loop.

**Files:**
- Create: `app/planner/service.py`, `app/planner/router.py`
- Modify: `app/main.py` (include the router), `app/diary/router.py` (call `replan_after_log` after `add_entry`)
- Test: `tests/test_planner_api.py`

**Interfaces:**
- Consumes: Tasks 1–4; `targets.service.resolve_day`, `profiles.service.get_*`, `diary.service.consumed_on / list_entries / skipped_on`, `foods.nutrition.compute_dish_nutrients / nutrients_for_portion`, `foods.measures.measures_for_food / resolve_grams / format_quantity`, `households.service.get_household_for_user / list_members`.
- Produces (service):

```python
class NoProfile(LookupError); class PlanItemNotFound(LookupError)
class ItemLocked(ValueError); class NoAlternative(LookupError)

week_start_for(day) -> datetime.date            # the Sunday on or before
local_today(user) -> datetime.date
portion_label(measure_name, quantity, grams) -> str
portion_ladder(measures: Sequence[Measure]) -> tuple[Portion, ...]
load_pool(db, user) -> list[Candidate]
build_context(db, user, profile, day) -> DayContext
get_plan(db, user, week_start) -> MealPlan | None
generate_week(db, user, week_start, *, reseed: bool = False) -> MealPlan
replan_after_log(db, user, day, slot, food_id) -> bool
set_locked(db, user, item_id, locked) -> MealPlan
swap_item(db, user, item_id) -> MealPlan
describe_week(db, user, plan) -> WeekView
cooking_view(db, user, day) -> list[Overlap]
```

- [ ] **Step 1: Write the failing API tests**

Create `tests/test_planner_api.py`:

```python
"""The meal planner, end to end: profile -> plan -> swap, lock, regenerate, re-plan.

Builds its own small pool on top of `reference_data`, so every assertion here is
about the planner's behaviour rather than about which of 72 seeded dishes won a
near-tie. Dates are in the coming week: the planner never plans a day that has
already ended, so a fixed date in the past would come back empty.
"""

import datetime
import uuid
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient, PortionMeasure
from app.models.household import HouseholdMember
from app.models.nutrient import Nutrient
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.planner import service as planner
from app.profiles import service as profiles
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")

# A week that has not started yet, so every day of it can be planned.
def upcoming_sunday() -> datetime.date:
    today = datetime.datetime.now(KOLKATA).date()
    days = (6 - today.weekday()) % 7
    return today + datetime.timedelta(days=days or 7)


WEEK = upcoming_sunday()
MONDAY = WEEK + datetime.timedelta(days=1)
FRIDAY = WEEK + datetime.timedelta(days=5)

# (code, name, per-100g nutrients, diet tags)
INGREDIENTS = [
    ("test:urad", "Urad dal", {"energy": 340, "protein": 25, "calcium": 150, "potassium": 900}, "vegetarian eggetarian fishetarian veg"),
    ("test:curd", "Curd, cow milk", {"energy": 60, "protein": 3, "calcium": 150, "vitamin_b12": 0.4}, "vegetarian eggetarian fishetarian veg"),
    ("test:egg", "Egg, whole", {"energy": 155, "protein": 13, "calcium": 50, "vitamin_b12": 1.1}, "eggetarian fishetarian"),
    ("test:chicken", "Chicken, meat", {"energy": 240, "protein": 27, "potassium": 250}, None),
    ("test:chana", "Bengal gram, whole", {"energy": 160, "protein": 9, "calcium": 50, "fibre": 8}, "vegetarian eggetarian fishetarian veg"),
    ("test:milk", "Milk, cow", {"energy": 60, "protein": 3, "calcium": 120, "vitamin_b12": 0.5}, "vegetarian eggetarian fishetarian veg"),
]

# (code, name, slot tags, diet tag, yield, [(ingredient code, raw grams)], [(measure, grams)])
DISHES = [
    ("test:idli", "Idli", "breakfast snack dinner", "vegetarian", 2.6,
     [("test:rice", 400), ("test:urad", 100)], [("1 idli", 45), ("3 idli", 135)]),
    ("test:sambar-rice", "Rice with sambar", "lunch dinner", "vegetarian", 2.5,
     [("test:rice", 300), ("test:urad", 100)], [("1 cup", 200)]),
    ("test:curd-rice", "Curd rice", "lunch dinner", "vegetarian", 1.2,
     [("test:rice", 300), ("test:curd", 200)], [("1 cup", 200)]),
    ("test:egg-curry", "Egg curry", "lunch dinner", "eggetarian", 1.0,
     [("test:egg", 200)], [("1 egg", 60)]),
    ("test:chicken-curry", "Chicken curry", "lunch dinner", "nonveg", 1.0,
     [("test:chicken", 300)], [("1 cup", 150)]),
    ("test:sundal", "Chana sundal", "snack", "vegetarian", 1.0,
     [("test:chana", 200)], [("1 katori", 100)]),
    ("test:coffee", "Filter coffee", "breakfast snack", "vegetarian", 1.0,
     [("test:milk", 150)], [("1 tumbler", 150)]),
]


@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """Seven dishes across every slot, one egg, one meat, one calcium-heavy drink."""
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    ingredients = {"test:rice": db.scalar(select(Ingredient).where(Ingredient.code == "test:rice"))}

    for code, name, values, tags in INGREDIENTS:
        ingredient = Ingredient(code=code, name=name, source="IFCT", diet_tags=tags)
        db.add(ingredient)
        db.flush()
        for nutrient_code, per_100g in values.items():
            db.add(IngredientNutrient(
                ingredient_id=ingredient.id, nutrient_id=nutrients[nutrient_code].id,
                per_100g=per_100g, source="IFCT",
            ))
        ingredients[code] = ingredient

    dishes = {}
    for code, name, slots, diet, yield_factor, recipe, measures in DISHES:
        dish = Dish(
            code=code, name=name, source="authored", is_editable=True,
            slot_tags=slots, diet_tags=diet, yield_factor=yield_factor,
        )
        db.add(dish)
        db.flush()
        for ingredient_code, grams in recipe:
            db.add(DishIngredient(
                dish_id=dish.id, ingredient_id=ingredients[ingredient_code].id, grams=grams,
            ))
        for index, (measure, grams) in enumerate(measures):
            db.add(PortionMeasure(
                dish_id=dish.id, measure_name=measure, grams=grams, is_default=(index == 0),
            ))
        dishes[code] = dish
    db.flush()
    return dishes


NON_VEG_PROFILE = {**PROFILE, "diet_type": "non-vegetarian"}


def week(api, start=WEEK):
    response = api.get(f"/plan/week?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def day_of(plan: dict, date: datetime.date) -> dict:
    return next(d for d in plan["days"] if d["date"] == str(date))


def item_in(plan: dict, date: datetime.date, slot: str) -> dict | None:
    return next((i for i in day_of(plan, date)["items"] if i["slot"] == slot), None)


def _user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


# --- shape and lifecycle ---------------------------------------------------------------


def test_the_plan_needs_a_profile(signed_in, planner_pool):
    assert signed_in.get(f"/plan/week?start={WEEK}").status_code == 404


def test_the_week_must_start_on_a_sunday(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    assert signed_in.get(f"/plan/week?start={MONDAY}").status_code == 422


def test_a_week_is_generated_on_first_request_sunday_to_saturday(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    plan = week(signed_in)

    assert plan["start_date"] == str(WEEK)
    assert [d["weekday"] for d in plan["days"]] == [
        "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    ]
    for day in plan["days"]:
        assert [i["slot"] for i in day["items"]] == [
            "breakfast", "snack1", "lunch", "snack2", "dinner",
        ]
        for item in day["items"]:
            assert item["dish_name"]
            assert item["portion"]
            assert item["locked"] is False


def test_asking_again_returns_the_stored_plan_not_a_new_one(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    first = week(signed_in)
    second = week(signed_in)

    assert [i["id"] for d in first["days"] for i in d["items"]] == [
        i["id"] for d in second["days"] for i in d["items"]
    ]


def test_portions_read_as_household_measures(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    portions = {i["portion"] for d in week(signed_in)["days"] for i in d["items"]}

    # Every portion is a count of a seeded measure -- "3 idli", "1½ cup" -- never bare grams.
    assert portions
    assert all(not p.endswith(" g") for p in portions)


def test_days_that_have_already_ended_are_not_planned(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    today = datetime.datetime.now(KOLKATA).date()
    this_week = planner.week_start_for(today)

    plan = week(signed_in, this_week)

    for day in plan["days"]:
        date = datetime.date.fromisoformat(day["date"])
        if date < today:
            assert day["items"] == []
        else:
            assert day["items"]


def test_an_empty_pool_gives_an_empty_but_valid_week(signed_in, reference_data):
    # `reference_data` seeds one dish with no slot tags, so nothing is plannable.
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    plan = week(signed_in)

    assert len(plan["days"]) == 7
    assert all(day["items"] == [] for day in plan["days"])


# --- constraints -----------------------------------------------------------------------------


def test_a_friday_rule_makes_friday_vegetarian_and_says_so(signed_in, planner_pool):
    signed_in.put(
        "/profile",
        json={
            **PROFILE,
            "diet_type": "eggetarian",
            "observances": [{"kind": "weekday", "weekday": 5, "label": ""}],
        },
    )

    plan = week(signed_in)
    friday = day_of(plan, FRIDAY)
    monday = day_of(plan, MONDAY)

    assert friday["vegetarian"] is True
    assert friday["vegetarian_reason"] == "your Friday rule"
    assert all(i["dish_name"] != "Egg curry" for i in friday["items"])
    assert monday["vegetarian"] is False
    assert monday["vegetarian_reason"] is None


def test_a_vegetarian_never_sees_egg_or_meat(signed_in, planner_pool):
    signed_in.put("/profile", json={**PROFILE, "diet_type": "vegetarian"})

    names = {i["dish_name"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "Egg curry" not in names
    assert "Chicken curry" not in names


def test_an_avoided_dish_is_never_suggested(signed_in, planner_pool):
    curd_rice = planner_pool["test:curd-rice"]
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "avoided": [{"label": "Curd rice", "food_id": str(curd_rice.id), "food_kind": "dish"}],
        },
    )

    names = {i["dish_name"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "Curd rice" not in names


def test_a_disabled_snack_slot_is_not_planned(signed_in, planner_pool):
    meal_times = [
        {**slot, "is_enabled": slot["slot"] != "snack1"} for slot in PROFILE["meal_times"]
    ]
    signed_in.put("/profile", json={**NON_VEG_PROFILE, "meal_times": meal_times})

    slots = {i["slot"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "snack1" not in slots
    assert "snack2" in slots


def test_a_skipped_meal_is_not_planned_for_that_day(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    signed_in.post("/diary/skips", json={"date": str(MONDAY), "slot": "dinner"})

    plan = week(signed_in)

    assert item_in(plan, MONDAY, "dinner") is None
    assert item_in(plan, MONDAY + datetime.timedelta(days=1), "dinner") is not None


# --- medication ------------------------------------------------------------------------


def test_calcium_heavy_food_stays_four_hours_clear_of_levothyroxine(signed_in, planner_pool):
    # Breakfast at 08:00 is one hour after the dose: inside the four-hour window,
    # so the milk coffee (180 mg calcium a tumbler) is refused there and idli is
    # the only breakfast left. Lunch at 13:30 is clear, so curd rice may appear.
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "conditions": ["hypothyroidism"],
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
        },
    )

    plan = week(signed_in)

    breakfasts = {i["dish_name"] for d in plan["days"] for i in d["items"] if i["slot"] == "breakfast"}
    assert breakfasts == {"Idli"}


def test_breakfast_inside_the_sixty_minute_window_says_when_to_eat(signed_in, planner_pool):
    meal_times = [
        {**slot, "time": "07:30"} if slot["slot"] == "breakfast" else slot
        for slot in PROFILE["meal_times"]
    ]
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "meal_times": meal_times,
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
        },
    )

    breakfast = item_in(week(signed_in), MONDAY, "breakfast")

    assert breakfast is not None
    assert "08:00" in breakfast["rationale"]


def test_potassium_is_not_pushed_for_a_hypertensive_on_an_ace_inhibitor(signed_in, planner_pool, db):
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "conditions": ["hypertension"],
            "medications": [{"name": "Ramipril", "time": "08:00"}],
        },
    )
    user = _user(db)

    context = planner.build_context(db, user, profiles.get_profile(db, user), MONDAY)

    # The baseline AI, not hypertension's 4,000 mg: raising potassium is unsafe
    # on ramipril, and the planner inherits that from the targets overlay.
    assert context.goals["potassium"].amount == 3510


def test_warfarin_holds_vitamin_k_steady_in_the_planner(signed_in, planner_pool, db):
    signed_in.put(
        "/profile",
        json={**NON_VEG_PROFILE, "medications": [{"name": "Warfarin", "time": "20:00"}]},
    )
    user = _user(db)

    context = planner.build_context(db, user, profiles.get_profile(db, user), MONDAY)

    assert context.hold_steady == frozenset({"vitamin_k"})


# --- editing the plan -------------------------------------------------------------------


def test_locking_survives_regeneration(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")

    locked = signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True})
    assert locked.status_code == 200
    assert item_in(locked.json(), MONDAY, "lunch")["locked"] is True

    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})
    assert regenerated.status_code == 200

    kept = item_in(regenerated.json(), MONDAY, "lunch")
    assert kept["id"] == lunch["id"]
    assert kept["dish_id"] == lunch["dish_id"]
    assert kept["locked"] is True

    unlocked = signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": False})
    assert item_in(unlocked.json(), MONDAY, "lunch")["locked"] is False


def test_regenerating_replaces_the_unlocked_items(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = {i["id"] for d in week(signed_in)["days"] for i in d["items"]}

    after_plan = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)}).json()
    after = {i["id"] for d in after_plan["days"] for i in d["items"]}

    assert before.isdisjoint(after)
    assert len(after) == len(before)


def test_swapping_replaces_only_that_dish(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    plan = week(signed_in)
    lunch = item_in(plan, MONDAY, "lunch")
    dinner = item_in(plan, MONDAY, "dinner")

    swapped = signed_in.post(f"/plan/items/{lunch['id']}/swap", json={})
    assert swapped.status_code == 200, swapped.text

    new_lunch = item_in(swapped.json(), MONDAY, "lunch")
    assert new_lunch["dish_id"] != lunch["dish_id"]
    assert item_in(swapped.json(), MONDAY, "dinner") == dinner


def test_a_locked_item_cannot_be_swapped(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")
    signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True})

    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 409


def test_someone_elses_item_is_not_found(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    week(signed_in)

    assert signed_in.patch(f"/plan/items/{uuid.uuid4()}", json={"locked": True}).status_code == 404


# --- deviation: re-plan the rest of the day ----------------------------------------------


def log(api, dish: Dish, on: datetime.date, slot: str) -> None:
    created = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": slot, "food_id": str(dish.id),
            "food_kind": "dish", "grams": 200, "is_estimated": False,
        },
    )
    assert created.status_code == 201, created.text


def test_logging_something_off_plan_replans_only_the_rest_of_that_day(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    planned_lunch = item_in(before, MONDAY, "lunch")
    off_plan = next(
        d for d in planner_pool.values()
        if str(d.id) != planned_lunch["dish_id"] and "lunch" in d.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")
    after = week(signed_in)

    # Earlier slots and the logged slot itself keep their rows.
    for slot in ("breakfast", "snack1", "lunch"):
        assert item_in(after, MONDAY, slot) == item_in(before, MONDAY, slot)
    # Later slots are re-planned around what was actually eaten.
    for slot in ("snack2", "dinner"):
        assert item_in(after, MONDAY, slot)["id"] != item_in(before, MONDAY, slot)["id"]
    # Every other day is untouched.
    for day in before["days"]:
        if day["date"] != str(MONDAY):
            assert day_of(after, datetime.date.fromisoformat(day["date"])) == day


def test_logging_the_planned_dish_changes_nothing(signed_in, planner_pool, db):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    planned = item_in(before, MONDAY, "lunch")
    dish = db.get(Dish, uuid.UUID(planned["dish_id"]))

    log(signed_in, dish, MONDAY, "lunch")

    assert week(signed_in) == before


def test_a_locked_dinner_survives_an_off_plan_lunch(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    dinner = item_in(before, MONDAY, "dinner")
    signed_in.patch(f"/plan/items/{dinner['id']}", json={"locked": True})
    planned_lunch = item_in(before, MONDAY, "lunch")
    off_plan = next(
        d for d in planner_pool.values()
        if str(d.id) != planned_lunch["dish_id"] and "lunch" in d.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")

    kept = item_in(week(signed_in), MONDAY, "dinner")
    assert kept["id"] == dinner["id"]
    assert kept["locked"] is True


# --- the household cooking view -------------------------------------------------------------


def test_a_solo_user_has_no_cooking_overlaps(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    week(signed_in)

    response = signed_in.get(f"/plan/cooking?date={MONDAY}")

    assert response.status_code == 200
    assert response.json() == {"date": str(MONDAY), "overlaps": []}


def test_the_cooking_view_names_members_whose_plans_share_a_dish(signed_in, planner_pool, db):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    household = signed_in.post("/households", json={"name": "Home"}).json()
    mine = item_in(week(signed_in), MONDAY, "lunch")

    amma = User(google_sub="sub-amma", email="amma@example.com", name="Amma")
    db.add(amma)
    db.flush()
    db.add(HouseholdMember(household_id=uuid.UUID(household["id"]), user_id=amma.id))
    plan = MealPlan(user_id=amma.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    db.add(MealPlanItem(
        plan_id=plan.id, plan_date=MONDAY, slot="lunch",
        dish_id=uuid.UUID(mine["dish_id"]), grams=200.0, measure_name="cup", quantity=1.0,
    ))
    # A second item that cannot coincide: sundal is never a breakfast candidate,
    # so the signed-in user's breakfast is idli or coffee and this stays unshared.
    db.add(MealPlanItem(
        plan_id=plan.id, plan_date=MONDAY, slot="breakfast",
        dish_id=planner_pool["test:sundal"].id, grams=100.0, measure_name="katori", quantity=1.0,
    ))
    db.flush()

    overlaps = signed_in.get(f"/plan/cooking?date={MONDAY}").json()["overlaps"]

    assert overlaps == [
        {"slot": "lunch", "dish_name": mine["dish_name"], "members": ["Amma", "Tracker"]},
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_planner_api.py -q -x`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.planner.service'`

- [ ] **Step 3: Write the service**

Create `app/planner/service.py`:

```python
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
from app.foods.measures import Measure, format_quantity, measures_for_food, resolve_grams
from app.foods.nutrition import compute_dish_nutrients, nutrients_for_portion
from app.households import service as households
from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.food import Dish, DishIngredient, Ingredient
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


def load_pool(db: Session, user: User) -> list[Candidate]:
    """Every dish the planner may consider, in a stable order.

    Only dishes with slot tags are plannable -- that is the authored set. INDB
    reference dishes carry no slots and no recipe, and are for logging what was
    eaten out rather than for suggesting what to cook.
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

    pool = []
    for dish in dishes:
        recipe = db.execute(
            select(Ingredient.id, Ingredient.name)
            .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
            .where(DishIngredient.dish_id == dish.id)
        ).all()
        measures = measures_for_food(db, dish.id, "dish")
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
                ingredient_ids=frozenset(row.id for row in recipe),
                ingredient_names=tuple(row.name for row in recipe),
                per_100g=compute_dish_nutrients(db, dish),
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
        logged=frozenset(entry.slot for entry in diary.list_entries(db, user, day)),
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
```

- [ ] **Step 4: Write the router and wire it up**

Create `app/planner/router.py`:

```python
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.user import User
from app.planner import rules, service

router = APIRouter(prefix="/plan", tags=["plan"])


class PlanItemOut(BaseModel):
    id: uuid.UUID
    slot: str
    dish_id: uuid.UUID
    dish_name: str
    portion: str
    locked: bool
    rationale: str | None


class PlanDayOut(BaseModel):
    date: datetime.date
    weekday: str
    vegetarian: bool
    vegetarian_reason: str | None
    items: list[PlanItemOut]


class WeekPlanOut(BaseModel):
    start_date: datetime.date
    days: list[PlanDayOut]


class RegenerateIn(BaseModel):
    start: datetime.date


class LockIn(BaseModel):
    locked: bool


class CookingOverlapOut(BaseModel):
    slot: str
    dish_name: str
    members: list[str]


class CookingViewOut(BaseModel):
    date: datetime.date
    overlaps: list[CookingOverlapOut]


def _week_out(db: Session, user: User, plan) -> WeekPlanOut:
    view = service.describe_week(db, user, plan)
    return WeekPlanOut(
        start_date=view.start_date,
        days=[
            PlanDayOut(
                date=day.date,
                weekday=day.weekday,
                vegetarian=day.vegetarian,
                vegetarian_reason=day.vegetarian_reason,
                items=[PlanItemOut(**vars(item)) for item in day.items],
            )
            for day in view.days
        ],
    )


def _require_sunday(start: datetime.date) -> None:
    if rules.sunday_index(start) != 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The plan week starts on a Sunday"
        )


@router.get("/week", response_model=WeekPlanOut)
def read_week(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    """The week's plan, generated and stored the first time it is asked for."""
    _require_sunday(start)
    plan = service.get_plan(db, user, start)
    if plan is None:
        try:
            plan = service.generate_week(db, user, start)
        except service.NoProfile as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
        db.commit()
    return _week_out(db, user, plan)


@router.post("/week/regenerate", response_model=WeekPlanOut)
def regenerate_week(
    payload: RegenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    _require_sunday(payload.start)
    try:
        plan = service.generate_week(db, user, payload.start, reseed=True)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.patch("/items/{item_id}", response_model=WeekPlanOut)
def lock_item(
    item_id: uuid.UUID,
    payload: LockIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    try:
        plan = service.set_locked(db, user, item_id, payload.locked)
    except service.PlanItemNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan item") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.post("/items/{item_id}/swap", response_model=WeekPlanOut)
def swap_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    try:
        plan = service.swap_item(db, user, item_id)
    except service.PlanItemNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan item") from exc
    except service.ItemLocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock this meal to swap it") from exc
    except service.NoAlternative as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No other dish fits this slot today"
        ) from exc
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.get("/cooking", response_model=CookingViewOut)
def read_cooking(
    date: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CookingViewOut:
    overlaps = service.cooking_view(db, user, date)
    return CookingViewOut(
        date=date,
        overlaps=[CookingOverlapOut(**vars(overlap)) for overlap in overlaps],
    )
```

In `app/main.py`: add `from app.planner.router import router as planner_router` (alphabetical, after `households`) and `app.include_router(planner_router)` after the diary router.

In `app/diary/router.py`: add `from app.planner import service as planner` and, in `create_entry`, immediately after the `service.add_entry(...)` block and before `db.commit()`:

```python
    # Eating something other than what was planned re-plans the rest of that
    # day -- only that day. The week is left alone unless the user asks.
    planner.replan_after_log(db, user, payload.date, payload.slot, payload.food_id)
```

- [ ] **Step 5: Run the planner tests, then the tracking tests the hook touches**

Run: `uv run pytest tests/test_planner_api.py tests/test_tracking_api.py tests/test_planner_engine.py tests/test_planner_rules.py -q && uv run ruff check .`
Expected: all PASS, ruff clean.

Likely failures and what they mean:
- `test_portions_read_as_household_measures` fails with a bare-gram label → `measures_for_food` returned only generic measures; check `PortionMeasure.dish_id` was set in the fixture.
- `test_calcium_heavy_food_stays_four_hours_clear_of_levothyroxine` shows "Filter coffee" at breakfast → `requirement` is empty; confirm `reference_data` seeds a calcium RDA row for the profile's sex (it does, 1000 for both).
- `test_logging_something_off_plan_replans_only_the_rest_of_that_day` sees an unchanged dinner id → `_store` did not delete rows in `open_slots`; check the `slot.in_` clause.

- [ ] **Step 6: Commit**

```bash
git add app/planner/service.py app/planner/router.py app/main.py app/diary/router.py tests/test_planner_api.py
git commit -m "feat(backend): add the meal plan API -- generate, swap, lock, regenerate, re-plan

GET /plan/week builds and stores the week the first time it is asked for. The
goals are each day's ledger-adjusted targets, so yesterday's shortfall is what
today's plan aims to close. Logged food is fixed and counted, which is what lets
one code path plan a week and re-plan the rest of an afternoon after an off-plan
lunch. Medication timing is a constraint here, not a note: nothing calcium-heavy
inside four hours of levothyroxine.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 6: Frontend — the Plan screen on the real endpoint

**Files:**
- Modify: `frontend/src/plan/PlanScreen.tsx`, `frontend/src/plan/usePlan.ts`, `frontend/src/plan/PlanScreen.test.tsx`, `frontend/src/mocks/handlers/index.ts`, `frontend/src/mocks/fixtures/plan.ts`
- Create: `frontend/src/plan/CookingView.tsx`

**Interfaces:**
- Consumes: the five endpoints from Task 5 (shapes already in `src/plan/types.ts`); `useHousehold` from `src/households/useHousehold.ts`; `ApiError` from `src/lib/api.ts`; `EmptyState`, `Skeleton` from `src/ui/feedback.tsx`; `Card`, `CardTitle` from `src/ui/Card.tsx`; `SLOT_LABELS` from `src/log/types.ts`.

- [ ] **Step 1: Rewrite the tests**

Replace `frontend/src/plan/PlanScreen.test.tsx` with:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { COOKING_FIXTURE, PLAN_FIXTURE } from '../mocks/fixtures/plan'
import { server } from '../mocks/server'
import { PlanScreen } from './PlanScreen'

/*
 * `/plan/week` is a real endpoint now, so it is stubbed per test. The fixture
 * stays because it carries the states worth asserting -- a Friday rule, a locked
 * meal, a rationale -- which a freshly generated plan would not reliably produce.
 * Solo by default: the cooking view only appears for a household member.
 */
beforeEach(() => {
  server.use(
    http.get(apiUrl('/plan/week'), () => HttpResponse.json(PLAN_FIXTURE)),
    http.get(apiUrl('/households/me'), () => new HttpResponse('no household', { status: 404 })),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Every day is rendered once and hidden on a phone with a CSS class, which jsdom
 * does not evaluate — so all seven are in the DOM here. Each day is a landmark
 * region, so queries scope to the day under test.
 */
async function day(weekday: string) {
  return within(await screen.findByRole('region', { name: weekday }))
}

test('shows the week Sunday to Saturday', async () => {
  renderScreen()

  expect(await screen.findByRole('radio', { name: /sunday/i })).toBeInTheDocument()
  expect(await screen.findByRole('radio', { name: /saturday/i })).toBeInTheDocument()
})

test('shows the planned dish for each slot of a day', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText('Ven pongal')).toBeInTheDocument()
  expect(sunday.getByText('Rice with sambar')).toBeInTheDocument()
})

test('selecting a day makes it the one the phone shows', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('radio', { name: /friday/i }))

  expect(screen.getByRole('radio', { name: /friday/i })).toBeChecked()
  expect(screen.getByRole('radio', { name: /sunday/i })).not.toBeChecked()
})

/*
 * Observance is a hard constraint, not a preference, and on those days egg counts
 * as non-vegetarian alongside meat and fish. If the plan silently drops non-veg
 * without saying why, the user cannot tell the rule was applied.
 */
test('says when a day is vegetarian and which rule made it so', async () => {
  renderScreen()

  const friday = await day('Friday')
  expect(friday.getByText(/vegetarian/i)).toBeInTheDocument()
  expect(friday.getByText(/your Friday rule/i)).toBeInTheDocument()
})

test('does not mark an ordinary day as vegetarian', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.queryByText(/vegetarian/i)).not.toBeInTheDocument()
})

// The planner is not a black box: the spec scores dishes on the nutrient gap they
// close, and saying so is what makes a suggestion trustworthy.
test('explains why a dish was chosen when the planner has a reason', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(/closes the morning protein gap/i)).toBeInTheDocument()
})

test('marks a locked meal so it is clear it survives regeneration', async () => {
  renderScreen()

  const monday = await day('Monday')
  expect(monday.getByText('Locked')).toBeInTheDocument()
})

// A locked meal that could still be swapped away would make the lock meaningless.
test('a locked meal cannot be swapped', async () => {
  renderScreen()

  const monday = await day('Monday')
  const lockedRow = monday.getByText('Curd rice with poriyal').closest('li')
  expect(within(lockedRow!).getByRole('button', { name: /swap/i })).toBeDisabled()
})

// The planner never plans a day that has already ended, so a plan fetched
// mid-week has empty earlier days. Empty must read as a fact, not a failure.
test('says when a day has nothing planned', async () => {
  server.use(
    http.get(apiUrl('/plan/week'), () =>
      HttpResponse.json({
        ...PLAN_FIXTURE,
        days: [{ ...PLAN_FIXTURE.days[0], items: [] }, ...PLAN_FIXTURE.days.slice(1)],
      }),
    ),
  )
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(/nothing planned/i)).toBeInTheDocument()
})

/*
 * The backend answers 404 when there is no profile, because a plan is built from
 * targets and there are none yet. That is not an error; it means onboarding.
 */
test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(
    http.get(apiUrl('/plan/week'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: /set up your profile/i })).toHaveAttribute(
    'href',
    '/profile/about',
  )
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('no longer calls itself demo data', async () => {
  renderScreen()

  await day('Sunday')
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

// Solo tracking is the complete experience; there is nothing to reconcile alone.
test('a solo user sees no cooking view', async () => {
  renderScreen()

  await day('Sunday')
  expect(screen.queryByText(/cooking together/i)).not.toBeInTheDocument()
})

test('a household member sees where plans coincide on the selected day', async () => {
  server.use(
    http.get(apiUrl('/households/me'), () =>
      HttpResponse.json({
        id: 'h1',
        name: 'Home',
        members: [
          { user_id: 'u1', name: 'Sudev', email: 's@example.com', share_progress: true, share_health: false },
          { user_id: 'u2', name: 'Amma', email: 'a@example.com', share_progress: true, share_health: false },
        ],
      }),
    ),
    http.get(apiUrl('/plan/cooking'), () => HttpResponse.json(COOKING_FIXTURE)),
  )
  renderScreen()

  const cooking = within(await screen.findByRole('region', { name: /cooking together/i }))
  expect(cooking.getByText('Idli with sambar')).toBeInTheDocument()
  expect(cooking.getByText(/Sudev, Amma/)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/plan`
Expected: the new tests fail (`nothing planned`, `set up your profile`, `no longer calls itself demo data`, both cooking tests); the older ones may fail too because `/plan/week` is still in the default handlers — that is fine, the next step fixes both.

- [ ] **Step 3: Remove the mocks and update the fixture's comment**

In `frontend/src/mocks/handlers/index.ts`, delete the five `// Plan 6 — the meal planner.` handlers and the `COOKING_FIXTURE, PLAN_FIXTURE` import. Update the module comment's second paragraph to read: "Nothing here shadows a real endpoint. Auth, households, food search, the whole tracking loop — profile, targets and diary — and the meal planner exist in FastAPI, so requests to them fall through to the real server in dev (`onUnhandledRequest: 'bypass'`) and are stubbed per-test in Vitest."

In `frontend/src/mocks/fixtures/plan.ts`, replace the header comment with:

```ts
/**
 * A Sunday-to-Saturday week with the constraints that make the planner
 * interesting: a recurring Friday vegetarian rule, a locked meal that must
 * survive regeneration, and breakfast pushed clear of the levothyroxine window.
 *
 * `/plan/week` and `/plan/cooking` are real endpoints now (plan 6). This fixture
 * is kept for `PlanScreen.test.tsx`, which stubs them per test: a generated plan
 * would not reliably produce a locked meal or a rationale to assert against.
 */
```

- [ ] **Step 4: Add `enabled` to `useCookingView` and build `CookingView`**

In `frontend/src/plan/usePlan.ts`, change `useCookingView` to:

```ts
export function useCookingView(date: string, enabled = true) {
  return useQuery({
    queryKey: ['plan', 'cooking', date],
    queryFn: () => api.get<CookingView>(`/plan/cooking?date=${date}`),
    retry: false,
    enabled,
  })
}
```

Create `frontend/src/plan/CookingView.tsx`:

```tsx
import { useHousehold } from '../households/useHousehold'
import { SLOT_LABELS } from '../log/types'
import { Card, CardTitle } from '../ui/Card'
import { Skeleton } from '../ui/feedback'
import { useCookingView } from './usePlan'

/**
 * Where household members' plans coincide on one day, so a dish can be cooked
 * once and portioned per person. Solo users never see it: there is nothing to
 * reconcile, and the spec is explicit that solo is the complete experience.
 */
export function CookingView({ date, weekday }: { date: string; weekday: string }) {
  const household = useHousehold()
  const inHousehold = household.data != null
  const cooking = useCookingView(date, inHousehold)

  if (!inHousehold) return null

  return (
    <section aria-labelledby="cooking-together" className="mb-4">
      <Card>
        <CardTitle>
          <span id="cooking-together">Cooking together</span>
        </CardTitle>
        {cooking.isPending && <Skeleton className="mt-2 h-10 w-full" />}
        {cooking.isError && (
          <p role="alert" className="mt-2 text-sm text-above-limit">
            The cooking view could not be loaded.
          </p>
        )}
        {cooking.data !== undefined && cooking.data.overlaps.length === 0 && (
          <p className="mt-2 text-sm text-text-muted">
            No two plans share a dish on {weekday}.
          </p>
        )}
        {cooking.data !== undefined && cooking.data.overlaps.length > 0 && (
          <ul className="mt-2 divide-y divide-border">
            {cooking.data.overlaps.map((overlap) => (
              <li key={`${overlap.slot}-${overlap.dish_name}`} className="py-2">
                <span className="text-xs text-text-muted">{SLOT_LABELS[overlap.slot]}</span>
                <p className="text-sm font-medium">{overlap.dish_name}</p>
                <p className="text-xs text-text-muted">{overlap.members.join(', ')}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}
```

Check `Card`'s props in `src/ui/Card.tsx` before using it: if it requires a `title` prop or wraps children differently, adapt the markup so the section still has the accessible name "Cooking together" (the `aria-labelledby` is what the test finds).

- [ ] **Step 5: Update `PlanScreen.tsx`**

Make these edits to `frontend/src/plan/PlanScreen.tsx`:

1. Imports: add `import { Link } from 'react-router-dom'`, `import { ApiError } from '../lib/api'`, `import { CookingView } from './CookingView'`; change the feedback import to `import { EmptyState, Skeleton } from '../ui/feedback'`.
2. In `DayPanel`, replace the `<ul>` with:

```tsx
      {day.items.length === 0 ? (
        <p className="px-3 py-3 text-sm text-text-muted">Nothing planned for this day.</p>
      ) : (
        <ul>
          {day.items.map((item) => (
            <ItemRow key={item.id} item={item} />
          ))}
        </ul>
      )}
```

3. In `PlanScreen`, after the `isPending` return and before the generic error return, add:

```tsx
  /*
   * A 404 from /plan/week means there is no profile yet: a plan is built from
   * the daily targets, and there are none to build from. Point at onboarding
   * rather than reporting an error that did not happen.
   */
  if (plan.error instanceof ApiError && plan.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description="A meal plan is built from your daily targets, so there is nothing to plan until you have told us about yourself."
        action={
          <Link
            to="/profile/about"
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface"
          >
            Set up your profile
          </Link>
        }
      />
    )
  }
```

4. Delete the `<DemoDataBanner endpoint="GET /plan/week" />` line.
5. Between the toolbar `div` and the days grid, add `<CookingView date={active.date} weekday={active.weekday} />`.

- [ ] **Step 6: Run the checks**

Run: `cd frontend && npx vitest run src/plan && npx tsc -b && npm run lint`
Expected: all plan tests PASS, tsc clean, oxlint clean. Then `npx vitest run` for the whole suite — nothing else imported the deleted handlers, so it should stay at 193 + the new cases.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/plan frontend/src/mocks/handlers/index.ts frontend/src/mocks/fixtures/plan.ts
git commit -m "feat(frontend): put the Plan screen on the real planner, with the cooking view

Deletes the last MSW handlers for /plan and the Demo data banner. A 404 now
points at onboarding, an empty day says so plainly, and household members get
the cooking view for the selected day. Solo users never see it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 7: End-to-end spec, READMEs, and the plan record

**Files:**
- Modify: `frontend/e2e/smoke.spec.ts` (append one test), `frontend/README.md`, `docs/superpowers/plans/README.md`, this file

- [ ] **Step 1: Append the Playwright test**

The plan needs a profile, and `globalSetup` resets the user once per run — so the test belongs at the end of the existing `test.describe('the tracking loop', ...)` block in `frontend/e2e/smoke.spec.ts`, after the Escape-key test, where it runs after onboarding. A separate file would sort before `smoke.spec.ts` and land on the empty state.

```ts
  test('the plan page shows a Sunday-to-Saturday week from the real planner', async ({
    page,
  }) => {
    // `scripts/e2e_seed.py` seeds no dishes with slot tags, so the plan it
    // produces is seven days with nothing in them. That is still the thing worth
    // checking: the screen is no longer on a fixture, the week comes out of
    // FastAPI Sunday to Saturday, and regenerating round-trips. Dish content
    // needs the full ETL, which is far too slow for CI.
    await page.goto('/plan')

    // Days are landmark regions named by weekday; at the default desktop
    // viewport all seven are visible side by side.
    await expect(page.getByRole('region', { name: 'Sunday' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Saturday' })).toBeVisible()

    // The demo banner is gone for good.
    await expect(page.getByRole('note')).toHaveCount(0)

    await page.getByRole('button', { name: /regenerate week/i }).click()
    await expect(page.getByRole('region', { name: 'Sunday' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
```

Also update the file's header comment list with a fourth bullet: "The Plan screen on the real planner, rather than the fixture it shipped with."

- [ ] **Step 2: Run it against the real stack**

From the repo root, with Postgres up (`docker compose up -d db`, already running in this session):

```bash
cd backend && uv run python -m scripts.e2e_seed
cd backend && (uv run uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &) && sleep 3 && curl -sf http://localhost:8000/health
cd frontend && npm run test:e2e
```

Expected: `4 passed`. Stop the API afterwards (`pkill -f "uvicorn app.main:app --port 8000"`). The e2e run uses the **development** database, which already carries the full ETL here, so locally the plan will show real dishes; in CI it shows empty days. Both satisfy the assertions.

- [ ] **Step 3: Update the frontend README**

In `frontend/README.md` under "Which screens are real", move Plan from the MSW list to the live list:

> **Live against the real backend:** sign-in, household, food search, the onboarding questionnaire, Today (real ICMR-NIN targets and the compensation ledger), meal logging, and the meal plan (generation, swap, lock, regenerate, and the household cooking view).
>
> **Still on MSW fixtures:** Report, Weight, Cycle and Reminders. Each carries a **Demo data** banner naming the endpoint it is waiting for. Those handlers and the `types.ts` in each feature folder are the proposed contract for the remaining backend plans.

Under "End to end", change "Playwright: onboarding -> log -> dashboard" to "Playwright: onboarding -> log -> dashboard, then the plan".

- [ ] **Step 4: Update the plans index and this file's status**

In `docs/superpowers/plans/README.md`, change row 6 to:

`| 6 | Meal planner | 7-day generation, swap/lock/regenerate, intra-day re-plan, household cooking view | **Complete** — `2026-09-02-meal-planner.md`. Generated on demand rather than on a Saturday schedule; one dish per slot (the paired snack beverage needs a beverage tag the seed data lacks) |`

Also add, after the paragraph about plan 5's follow-ups: "Plan 6's decisions and the gaps it leaves are recorded at the top and bottom of `2026-09-02-meal-planner.md`."

In this file, add a `**Status:**` line under the Spec line at the top, in the form the other plans use: test counts from the final run, and the checks that passed.

- [ ] **Step 5: Run everything**

```bash
cd backend  && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npx vitest run && npx tsc -b && npm run lint && npm run build
```

Expected: every command clean. Record the counts in the Status line.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e frontend/README.md docs/superpowers/plans/README.md docs/superpowers/plans/2026-09-02-meal-planner.md
git commit -m "docs: record plan 6, the meal planner, and add its end-to-end spec

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Known gaps to record in the closeout

- **Paired snack beverage.** The spec wants snack slots to propose a beverage alongside the snack. The seed data has no beverage tag, and inferring one from the default measure ("tumbler", "glass") would misclassify kanji and payasam. One item per slot until dishes carry the tag.
- **Saturday-evening generation.** On demand for now; the scheduler arrives with plan 8's reminders.
- **Statin and grapefruit; metformin with a meal.** Still unencoded, as the spec says they must be re-verified against a drug reference first. Deferred with `drug_interaction_rules` to phase 2.
- **Custom dishes are not yet plannable.** Users cannot create dishes yet, so `created_by_user_id` visibility is implemented but untested against real rows.
- **The 60-minute rule is advice, not a constraint.** The planner cannot move a meal time, which is a profile setting; it says when the first meal may be eaten. The 4-hour mineral rule *is* a constraint.
- **Vitamin K on warfarin** is held steady only against the previous day, and only for planned food. A logged day with wildly different vitamin K resets the reference point.
