# Weight & Cycle Implementation Plan (plan 7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weekly weigh-ins that recalibrate the calorie target by bounded steps, and optional, symptom-driven cycle tracking that coaches without ever moving the iron or calorie target. Together they replace the last two MSW fixtures in the More section. The plan also adds a postmenopausal status to the profile, with the iron fallback it selects.

**Architecture:**
- Two pure modules sit beside the existing engines and never touch the database:
  - `app/nutrition_core/recalibration.py`: smoothing, the trend slope, the expected trajectory, the floor and the bounded step.
  - `app/cycle/rules.py`: bleeding runs, the heavy-bleeding referral, and coaching selection.
- `app/weight/service.py` stores weigh-ins and the steps they cause, in `weight_logs` and `calorie_adjustments`.
- `resolve_day` reads the offset in force on each date and passes it into `build_targets`. The macros, the energy-scaled B vitamins, the ledger, the Today screen and the planner therefore all follow one figure.
- `app/cycle/service.py` stores `cycle_settings`, `cycle_logs`, `cycle_symptoms` and `cycle_screenings`. Nothing in the targets path reads them.
- A new `profiles.menstrual_status` column selects the postmenopausal iron row.
- The routers implement the contracts in `frontend/src/weight/types.ts` and `frontend/src/cycle/types.ts`. Those contracts are amended where the proposal could not express the spec, and both sides change together.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic and pytest on the backend; React 19, TanStack Query, MSW, Vitest, Recharts and Playwright on the frontend. No new dependencies are needed: recalibration is a least-squares slope and a few clamps.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`. This plan implements these sections:
- "4. Weight-driven adjustment"
- "8. Menstrual cycle awareness"
- "Solo Use & Households" (weight and cycle are private by default)
- "Data Model"
- "Testing & Verification": the cycle regression tests, and manual steps 8, 14 and 15
- "Safety": every string of cycle copy

The HTTP contracts are `frontend/src/weight/types.ts` and `frontend/src/cycle/types.ts`, with fixtures in `frontend/src/mocks/fixtures/more.ts`.

**Status:** Complete. 615 backend tests and 229 frontend tests passing, plus 7 Playwright
end-to-end tests; `ruff`, `alembic check`, `tsc -b`, `oxlint` and `vite build` clean.

## Global Constraints

**Backend tooling**
- Python `>=3.12` and `ruff` line length 100. Use `uv run` for every backend command, run from `backend/`.
- Ruff 0.16 runs its broad default rule set, because `pyproject.toml` has no `select`. The rules that bite here:
  - DTZ: never a naive `datetime.datetime.now()` or `datetime.date.today()`.
  - I001: import order.
  - RUF022: `__all__` sorted.
  - UP, B, SIM and PT.
- E501 is not enabled, but keep lines at 100 columns or fewer anyway. Do not add `noqa`.
- Code blocks in this plan are written for reading. Wrap any line over 100 columns before committing.

**Models and migrations**
- Every table extends `TimestampedBase`, which gives a UUID `id` and `created_at`. Register every model in `app/models/__init__.py` and keep `__all__` sorted.
- The test database runs against the **migrated** schema, never `create_all`. After adding a migration, run both of these, or every test fails with a `UsageError` naming the fix:
  - `DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head`
  - `uv run alembic upgrade head` (the development database)

  Then run `uv run alembic check`. The model is the source of truth.
- `alembic/script.py.mako` generates a header that fails ruff. Copy the header of `alembic/versions/d8e9f0a1b2c3_meal_plans.py` instead.

**Running tests**
- The full backend suite takes about 5 minutes. During a task, run only the test files you touched. The final task runs everything.
- Never run two pytest sessions against the shared test database at once.

**API conventions**
- Routers commit and services never do: services call `db.add` and `db.flush`, and the router calls `db.commit()` once before it returns.
- A 422 uses `status.HTTP_422_UNPROCESSABLE_CONTENT`.
- An endpoint that needs a profile answers 404 `"Complete your profile first"` when there is none.
- Responses are declared inline in the router as `XxxIn` / `XxxOut` pydantic models. Every route has both `response_model=` and a return annotation.

**Dates**
- A user's "today" is always `app.local_time.local_today(user)`, which Task 4 creates.
- Tests that depend on "today" compute dates from `datetime.datetime.now(ZoneInfo("Asia/Kolkata"))`. Fixed dates work only for date-parameterised reads.
- From Task 5 on, every `PUT /profile` whose weight differs from the latest weigh-in records a weigh-in dated today.

**Profile-save trap**
- Never add a weight or cycle table to `profiles.service.CHILD_MODELS`. A profile save deletes every table in that tuple.
- A weigh-in writes `Profile.weight_kg` directly on the row, never by calling `save_profile`.

**Frontend checks**
- Run `npx tsc -b` (never `--noEmit` alone), `npx vitest run`, `npm run lint` (oxlint) and `npm run build`.
- Tests stub real endpoints per test with `server.use(...)`, and an unhandled request fails the test.
- Each test file builds its own `QueryClient` with `retry: false`, wrapped in `MemoryRouter` when the screen has a `Link`.

**Cycle copy.** The spec's Safety section binds every string of cycle copy:
- Evidence is labelled, not laundered.
- Nutrition is never a substitute for treatment: NSAIDs outperform every dietary option for period pain, and heavy bleeding needs a clinician.
- No chocolate-craving copy.
- No copy suggesting more food in the luteal phase.
- Referral copy says "adolescents", which is what the source says, not "people".

**Commits**
- Commit after each task, on the current branch `tracking-loop-and-ui-foundation`. Do not push.
- Messages follow the repo's style: a conventional prefix (`feat(backend):`, `feat(frontend):`, `test:`, `docs:`), then a prose body that explains the *why*.
- Every message ends with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Decisions taken before starting

Recorded here so the implementer does not re-litigate them; the closeout carries them forward.

**Weight**

- **The profile's weight is the latest weigh-in.**
  - A weigh-in writes `profiles.weight_kg`.
  - A profile save whose weight differs from the latest weigh-in records a weigh-in dated today. Onboarding therefore records weigh-in number one.
  - Keeping one number, with one history, means protein and the energy formula follow measured weight, as the spec requires. It also means the trend starts from the onboarding weight rather than from nothing.
  - The row is written directly, never through `save_profile`.
- **A recalibration is a stored offset from the formula, not a stored calorie figure.**
  - `calorie_adjustments` holds the total kcal offset in force from a date on.
  - The formula is re-evaluated at the current weight every time, so the offset corrects only what the formula misses. Storing an absolute figure would count twice a weight change that the formula already follows.
  - It is stored rather than derived because a step depends on the goal in force when it was taken, and there is no goal history to replay.
- **How the trend is read.**
  - Smoothed weight is the mean of the last three weigh-ins.
  - Observed rate is the least-squares slope over the weigh-ins in the last 28 days that are also on or after the last step. It needs at least three weigh-ins spanning at least 14 days.
  - Expected rate comes from the formula target's real deficit, `(target − TEE) × 7 / 7700`, not from the pace's nominal figure. The BMR clamp shrinks the deficit for small sedentary users. A 55 kg sedentary woman on a steady loss sits on her BMR and should expect about 0.32 kg/week, not 0.5. Holding her to 0.5 would read an on-track trend as a stall.
  - Spec manual step 8 says "two weigh-ins". This plan needs three, because two weigh-ins give only one interval, and the spec's own "smoothed over the last 2–3 weigh-ins" and "sustained drift" rule that out.
- **How a step is sized.**
  - Drift under 0.25 kg/week is left alone.
  - Beyond that, the offset moves by half the energy-balance figure (1 kg/week ≈ 1,100 kcal/day). A slope fitted to three or four points is noisy, and correcting it in full overshoots.
  - The total offset stays within ±10% of the formula and does not compound past that bound.
  - The offset is truncated toward zero, to whole tens of kcal.
  - A downward step never takes the target below `min(formula, max(BMR, safe floor))`. The safe floor is 1,200 kcal for women and 1,500 kcal for men, the conventional floor for calorie restriction without medical supervision.
  - The BMR is the uncorrected FAO/WHO/UNU one that `energy_target` already clamps against.
- **The loss target itself gets the safe floor.** Until now `energy_target` clamped a loss goal only at BMR, which sits under 1,200/1,500 kcal for many smaller and older people. A 70-year-old woman at 42 kg was given 1,050 kcal. `energy_target` now clamps a loss goal at `max(BMR, min(maintenance, safe floor))`. The `min` stops a loss goal ever asking for more than maintenance, which is the case for a very small older man whose maintenance is itself under 1,500. Such a user is the only one who can sit below the safe floor, and recalibration never lowers them. Maintain and gain are unchanged, as is every ICMR golden value.
- **Steps are event-driven, and only today's weigh-in takes one.**
  - A step is evaluated when a weigh-in dated the user's today is posted and is the newest weigh-in. A step dated earlier would change the target of days that are already over. A weigh-in dated in the past therefore only fills in history, and the next weigh-in dated today reads it into the trend. There is no scheduler until plan 8.
  - Correcting or deleting a weigh-in that the step in force was read from re-reads that step at its own date. A typo therefore cannot leave a 10% cut standing. A new back-dated weigh-in still moves nothing.
  - A change of goal, pace or activity resets the offset to zero from today and restarts the trend window.
- **The offset moves the energy-scaled B vitamins.**
  - Thiamine, riboflavin, niacin and B6 are stored per activity level. While an offset is active they scale by `recalibrated ÷ formula`, EAR and RDA alike.
  - With no offset the ratio is exactly 1, so no existing target moves.
- **The energy ledger gets the same floor.**
  - Energy is compensable and excess-sensitive. Carries from two source days add up, so two surplus days could take `target_effective` down to 40% of the target. That is far below BMR, and the planner sizes portions from it.
  - The ledger's energy policy therefore uses the recalibration floor as its EAR.
  - `NutrientOut.ear` for energy stays null, so the Today status bands do not change.
- **A step never rewrites a stored plan.**
  - `generate_week` replaces every unlocked item, and a swap is not a lock. Regenerating on a step would silently throw away the user's swaps because they weighed in, which breaks the spec's "customizable" plan.
  - This week's stored portions stay as they were sized. The Plan screen's Regenerate re-sizes them when the user asks.
  - Everything planned afterwards uses the new target: an unplanned week, a regenerated week, and the deviation re-plan after a log. This is how a goal change already behaves.
- **Today explains a moved target.** While an offset is active, `resolve_day` adds a `calorie-recalibrated` warning, so the energy figure never moves without an explanation.

**Iron and the profile**

- **Postmenopausal status lives on the profile.** The field is `menstrual_status`, with the values `menstruating | postmenopausal | null`. It is null for men, and for women's profiles saved before this plan.
  - A postmenopausal woman gets the female 60+ iron row (IOM, 8 mg), whatever her age band.
  - Every other nutrient keeps its band. The 60+ band carries only four nutrients, so switching bands would drop fourteen targets.
  - Whenever the iron reference in use is the IOM row, `resolve_day` adds a `reference-framework` note. This also gives women over 60 the note they have been missing.
  - For postmenopausal women, a day's iron at 80% or more of the 45 mg upper limit adds an `approaching-limit` warning. After menopause the body has no route to excrete iron.
  - Pregnancy and lactation are out of scope and are recorded as a gap.

**Cycle**

- **Cycle tracking is for women who menstruate.** `GET /cycle` answers `eligible: false` for a male or postmenopausal profile, and enabling it is refused with 409. The postmenopausal screen says that any bleeding after menopause should be checked by a clinician.
- **Cycle data is logged by day.** A day has a flow (or none) plus symptoms, stored in `cycle_logs` and `cycle_symptoms`.
  - The symptom vocabulary is `cramps | bloating | breast_tenderness | low_mood`: the symptoms the coaching responds to.
  - There is no cravings symptom, per the spec's warning about the chocolate-craving script.
- **Coaching is symptom-driven, never calendar-driven.**
  - Coffee/tea timing (strong evidence) and calcium (moderate, guideline-endorsed) always show while tracking is on.
  - The calcium note names any PMS symptoms logged in the last 30 days.
  - Vitamin-C pairing shows when bleeding was logged in the last 7 days.
  - Ginger (moderate) and fenugreek (low) show only when cramps were logged during a bleed that is on its day 1–3 today. Days are counted from logged bleeding, never from a predicted phase.
  - Every note carries its evidence grade.
- **Heavy bleeding produces a referral, never a target change.**
  - The four screening questions cover soaking a pad or tampon in two hours or less, periods longer than seven days, clots larger than a ₹10 coin, and flooding. Answers are stored per answer date.
  - Any "yes" on the latest answers produces `referral`. So do more than seven consecutive logged bleeding days in the last 90.
  - Flow logged as "heavy" does not produce a referral on its own, because it is not a validated trigger.
- **Cycle data never reaches the targets path.** No cycle table is read by `resolve_day`, the ledger, recalibration or the planner. Regression tests lock this and say why.

**Privacy**

- Weight and cycle data fall under `household_members.share_health`, which is private by default.
- No endpoint exposes another member's weight or cycle data. `GET /weight` and `GET /cycle` read only the caller's own rows.
- `DELETE /cycle` erases every cycle row the user has.

---

## File structure

Paths are relative to `backend/` or `frontend/`.

**Backend — create**

| File | Responsibility |
|---|---|
| `app/local_time.py` | `local_today(user)`, the one helper for a user's calendar date (with a UTC fallback) |
| `app/nutrition_core/recalibration.py` | Pure: smoothing, trend points, observed and expected rates, the floor, the bounded step, reason and note text |
| `app/models/weight.py` | `WeightLog`, `CalorieAdjustment` |
| `app/models/cycle.py` | `CycleSettings`, `CycleLog`, `CycleSymptom`, `CycleScreening` |
| `alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py` | The six tables, plus `profiles.menstrual_status` |
| `app/weight/__init__.py`, `app/weight/service.py` | Weigh-ins, steps, resets, the trend view |
| `app/weight/router.py` | `GET /weight`, `POST /weight`, `DELETE /weight/{date}` |
| `app/cycle/__init__.py`, `app/cycle/rules.py` | Pure: bleeds, bleed day, referral, coaching notes |
| `app/cycle/service.py` | Settings, days, screenings, erase, the state view |
| `app/cycle/router.py` | `GET/PATCH/DELETE /cycle`, `PUT/DELETE /cycle/days/{date}`, `POST /cycle/screening` |
| `tests/test_recalibration.py` | Pure recalibration tests |
| `tests/test_weight_cycle_models.py` | One row per day, enforced by the database |
| `tests/test_weight_service.py` | Weigh-ins, steps and `resolve_day` against the database |
| `tests/test_weight_api.py` | The weight API and the profile hooks |
| `tests/test_menstrual_status.py` | Postmenopausal iron and its notes |
| `tests/test_cycle_rules.py` | Pure cycle rules |
| `tests/test_cycle_api.py` | The cycle API, and the locked iron and calorie rules |

**Backend — modify**

| File | Change |
|---|---|
| `app/nutrition_core/energy.py` | `SAFE_FLOOR_KCAL`; a loss target is floored at `max(BMR, min(maintenance, safe floor))` |
| `app/nutrition_core/targets.py` | `energy_offset_kcal` keyword on `build_targets`; `ENERGY_SCALED_REFERENCES`; `ReferenceValue.source` |
| `app/nutrition_core/conditions.py` | The `Warning.kind` comment lists the new kinds |
| `app/targets/service.py` | Reads the offset; energy floor in the ledger; recalibration, framework and iron-limit warnings; postmenopausal iron row; `source` on references |
| `app/profiles/service.py` | `body_of(profile)`; `menstrual_status` in the saved fields |
| `app/profiles/router.py` | `menstrual_status` in and out; weigh-in on a weight change; reset on a goal change; `local_today` |
| `app/planner/service.py` | `local_today` comes from `app.local_time` |
| `app/models/profile.py` | `menstrual_status` column |
| `app/models/__init__.py` | Six models registered |
| `app/main.py` | Two routers included |
| `scripts/e2e_session.py` | `OWNED_MODELS` gains the six tables and `MealPlan` |
| `tests/conftest.py` | `iron_reference` fixture |
| `tests/test_targets.py` | Offset tests |
| `tests/test_energy.py` | The safe floor on a loss target |

**Frontend — modify (and create where marked)**

| File | Change |
|---|---|
| `src/weight/types.ts` | The contract as built: nullable smoothing, observed rate, `since`, `note`, `NewWeighIn` |
| `src/weight/useWeight.ts` (create) | Query and mutations; a weigh-in invalidates weight, targets, profile and plan |
| `src/weight/WeightScreen.tsx` | Live endpoint: dated entry, validation, summary, chart from two weigh-ins, list with remove, adjustment card, 404 empty state |
| `src/weight/WeightScreen.test.tsx` (create) | Screen tests |
| `src/cycle/types.ts` | The contract as built: eligibility, days with symptoms, screening |
| `src/cycle/useCycle.ts` (create) | Query and mutations |
| `src/cycle/CycleDayForm.tsx` (create) | Log a day: date, flow, symptoms |
| `src/cycle/ScreeningCard.tsx` (create) | The four heavy-bleeding questions |
| `src/cycle/CycleScreen.tsx` | Live endpoint, eligibility states, logging, screening, erase, corrected referral copy |
| `src/cycle/CycleScreen.test.tsx` | Stubs the real endpoint; new tests |
| `src/lib/format.ts`, `src/lib/format.test.ts` | `formatDay(iso)` |
| `src/mocks/fixtures/more.ts` | Fixtures match the built contracts |
| `src/mocks/handlers/index.ts` | Weight and cycle handlers deleted |
| `src/onboarding/types.ts`, `validation.ts`, `steps.tsx`, `useProfile.ts`, `OnboardingWizard.tsx` | `menstrual_status`; a profile save also refreshes weight and cycle |
| `src/onboarding/validation.test.ts`, `useProfile.test.ts`, `OnboardingWizard.test.tsx` | Tests for the new question |
| `src/profile/ProfileScreen.tsx`, `ProfileScreen.test.tsx` | Shows the answer |
| `src/today/types.ts`, `src/today/TodayScreen.tsx`, `src/today/TodayScreen.test.tsx` | Three new warning kinds; unique keys |
| `e2e/smoke.spec.ts` | Weight and cycle walks appended |
| `README.md` | Which screens are real |

**Docs — modify:**
- `docs/superpowers/plans/README.md`
- this plan's Status line
- `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`: its contract table, for the amended endpoints

---
## Task 1: Recalibration arithmetic (pure)

Everything the weight feature decides lives in one module with no database access, so that every bound the spec names can be tested directly. Later tasks only choose which weigh-ins exist.

**Files:**
- Create: `app/nutrition_core/recalibration.py`
- Modify: `app/nutrition_core/energy.py` (`SAFE_FLOOR_KCAL`, and the loss clamp)
- Test: `tests/test_recalibration.py` (create), `tests/test_energy.py` (append)

**Interfaces (produced, used by Tasks 2, 4 and 5):**
```python
@dataclass(frozen=True)
class WeighIn: date: datetime.date; weight_kg: float

@dataclass(frozen=True)
class Step:
    offset_kcal: float          # the new TOTAL offset from the formula, not the change
    expected_kg_per_week: float
    observed_kg_per_week: float
    reason: str

SAFE_FLOOR_KCAL: dict[str, float]      # in energy.py, re-exported here: {"female": 1200.0, "male": 1500.0}
MAX_OFFSET_SHARE: float                # 0.10
def smoothed_weight(weigh_ins: Sequence[WeighIn]) -> float | None
def trend_points(weigh_ins: Sequence[WeighIn], as_of: date, since: date | None) -> list[WeighIn]
def observed_rate(points: Sequence[WeighIn]) -> float | None          # kg/week
def expected_rate(body: Body, goal: str, pace: str | None) -> float   # kg/week, negative = loss
def lowest_target(body: Body, formula_kcal: float) -> float
def recalibrated_energy(body: Body, formula_kcal: float, offset_kcal: float) -> float
def next_step(body, goal, pace, current_offset_kcal: float, points) -> Step | None
def trend_note(body, goal, pace, current_offset_kcal, points, stepped_on: date | None) -> str | None
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recalibration.py`:

```python
"""Weight-driven recalibration: the arithmetic, and the bounds the spec requires.

The reference man throughout is 25 y, 65 kg and sedentary: formula target 2,105.3
kcal on "maintain", uncorrected FAO/WHO/UNU BMR 1,670.9 kcal.
"""

import datetime

import pytest

from app.nutrition_core.energy import Body, basal_metabolic_rate, energy_target
from app.nutrition_core.recalibration import (
    MAX_OFFSET_SHARE,
    WeighIn,
    expected_rate,
    lowest_target,
    next_step,
    observed_rate,
    recalibrated_energy,
    smoothed_weight,
    trend_note,
    trend_points,
)

MAN = Body(sex="male", age=25, weight_kg=65.0, activity="sedentary")
WOMAN = Body(sex="female", age=25, weight_kg=55.0, activity="sedentary")
OLDER_WOMAN = Body(sex="female", age=70, weight_kg=42.0, activity="sedentary")
HEAVY_MAN = Body(sex="male", age=45, weight_kg=80.0, activity="moderate")

DAY0 = datetime.date(2026, 8, 3)


def weekly(*weights: float) -> list[WeighIn]:
    return [WeighIn(DAY0 + datetime.timedelta(weeks=i), kg) for i, kg in enumerate(weights)]


# --- smoothing and the trend ----------------------------------------------------------------


def test_smoothing_averages_the_last_three_weigh_ins():
    assert smoothed_weight(weekly(74.8, 74.9, 74.4, 74.1, 74.2)) == pytest.approx(74.233, abs=1e-3)


def test_smoothing_uses_what_there_is_before_the_third_weigh_in():
    assert smoothed_weight(weekly(70.0)) == 70.0


def test_there_is_no_smoothed_weight_before_the_first_weigh_in():
    assert smoothed_weight([]) is None


def test_the_observed_rate_is_the_fitted_slope_in_kg_per_week():
    assert observed_rate(weekly(70.0, 70.5, 71.0)) == pytest.approx(0.5)


def test_two_weigh_ins_are_not_a_trend():
    assert observed_rate(weekly(70.0, 71.0)) is None


def test_three_weigh_ins_inside_two_weeks_are_not_a_trend():
    points = [
        WeighIn(DAY0, 70.0),
        WeighIn(DAY0 + datetime.timedelta(days=6), 70.5),
        WeighIn(DAY0 + datetime.timedelta(days=13), 71.0),
    ]
    assert observed_rate(points) is None


def test_the_trend_reads_the_last_four_weeks_only():
    history = weekly(80.0, 70.0, 70.0, 70.0, 70.0, 70.0)
    points = trend_points(history, as_of=DAY0 + datetime.timedelta(weeks=5), since=None)
    assert [p.weight_kg for p in points] == [70.0] * 5


def test_the_trend_restarts_at_the_last_step():
    history = weekly(70.0, 70.5, 71.0, 71.5)
    points = trend_points(
        history,
        as_of=DAY0 + datetime.timedelta(weeks=3),
        since=DAY0 + datetime.timedelta(weeks=2),
    )
    assert [p.weight_kg for p in points] == [71.0, 71.5]


# --- the expected trajectory ----------------------------------------------------------------


def test_maintaining_expects_no_change():
    assert expected_rate(MAN, "maintain", None) == 0.0


def test_a_steady_gain_expects_half_a_kilo_a_week():
    assert expected_rate(MAN, "gain", "steady") == pytest.approx(0.5)


def test_a_clamped_loss_expects_what_the_real_deficit_delivers():
    # A steady loss names 0.5 kg/week, but the BMR clamp leaves him a 434 kcal/day
    # deficit and her 357. Holding them to 0.5 would read an on-track trend as a stall.
    assert expected_rate(MAN, "lose", "steady") == pytest.approx(-0.395, abs=1e-3)
    assert expected_rate(WOMAN, "lose", "steady") == pytest.approx(-0.324, abs=1e-3)


# --- the bound and the floor ----------------------------------------------------------------


def test_no_offset_leaves_the_formula_exactly_alone():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert recalibrated_energy(MAN, formula, 0.0) == formula


def test_the_offset_is_bounded_to_ten_percent_of_the_formula():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert recalibrated_energy(MAN, formula, -500.0) == pytest.approx(formula * 0.9)
    assert recalibrated_energy(MAN, formula, 500.0) == pytest.approx(formula * 1.1)


def test_the_floor_is_bmr_when_bmr_is_above_the_safe_minimum():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert lowest_target(MAN, formula) == pytest.approx(basal_metabolic_rate(MAN))


def test_the_floor_is_the_safe_minimum_when_bmr_is_below_it():
    small = Body(sex="female", age=40, weight_kg=42.0, activity="sedentary")  # BMR 1,186.9
    formula = energy_target(small, goal="maintain", pace=None)
    assert lowest_target(small, formula) == 1200.0


def test_a_target_on_the_safe_floor_is_never_pushed_below_it():
    # Lose/gentle for a 70-year-old at 42 kg would be 1,049.9 kcal; the safe floor
    # lifts it to 1,200, and recalibration cannot take it back down.
    formula = energy_target(OLDER_WOMAN, goal="lose", pace="gentle")
    assert formula == 1200.0
    assert lowest_target(OLDER_WOMAN, formula) == pytest.approx(formula)
    assert recalibrated_energy(OLDER_WOMAN, formula, -100.0) == pytest.approx(formula)


@pytest.mark.parametrize("body", [MAN, WOMAN, OLDER_WOMAN, HEAVY_MAN])
@pytest.mark.parametrize(
    ("goal", "pace"), [("lose", "gentle"), ("lose", "steady"), ("maintain", None), ("gain", "steady")]
)
@pytest.mark.parametrize("offset", [-1000.0, -210.0, 0.0, 210.0, 1000.0])
def test_a_recalibrated_target_never_leaves_its_bounds(body, goal, pace, offset):
    formula = energy_target(body, goal=goal, pace=pace)
    kcal = recalibrated_energy(body, formula, offset)

    assert kcal >= basal_metabolic_rate(body) - 1e-9
    assert kcal >= lowest_target(body, formula) - 1e-9
    assert kcal <= formula * (1 + MAX_OFFSET_SHARE) + 1e-9


# --- steps ----------------------------------------------------------------------------------


def test_a_sustained_gain_on_maintain_takes_a_step_down():
    step = next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.5, 66.0))

    # 0.5 kg/week of drift, half-corrected, is 275 kcal: bounded to 10% (210.5 kcal)
    # and kept to whole tens.
    assert step.offset_kcal == -210.0
    assert step.observed_kg_per_week == pytest.approx(0.5)
    assert step.expected_kg_per_week == 0.0


def test_losing_on_maintain_takes_a_step_up():
    step = next_step(MAN, "maintain", None, 0.0, weekly(66.0, 65.7, 65.4))

    # 0.3 kg/week × 1,100 × 0.5 = 165 kcal, truncated to 160.
    assert step.offset_kcal == 160.0


def test_drift_inside_the_tolerance_takes_no_step():
    assert next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.1, 65.2)) is None


def test_steps_do_not_compound_past_the_bound():
    assert next_step(MAN, "maintain", None, -210.0, weekly(66.0, 66.5, 67.0)) is None


def test_a_target_on_the_bmr_floor_takes_no_step_down():
    # A steady loss already clamps him at BMR, so a stalled trend has nowhere to push.
    assert next_step(MAN, "lose", "steady", 0.0, weekly(65.0, 65.0, 65.0)) is None


def test_the_reason_says_what_happened_in_plain_words():
    step = next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.5, 66.0))

    assert "risen about 0.5 kg a week" in step.reason
    assert "holding steady" in step.reason
    assert "moves down" in step.reason


# --- the note on the weight screen ----------------------------------------------------------


def test_the_note_asks_for_more_weigh_ins_before_there_is_a_trend():
    note = trend_note(MAN, "maintain", None, 0.0, weekly(65.0), stepped_on=None)
    assert "three weigh-ins" in note


def test_the_note_after_a_step_says_when_the_target_moved():
    note = trend_note(MAN, "maintain", None, -210.0, weekly(65.0), stepped_on=DAY0)
    assert "3 August" in note


def test_the_note_explains_a_target_that_cannot_move_further():
    note = trend_note(MAN, "lose", "steady", 0.0, weekly(65.0, 65.0, 65.0), stepped_on=None)
    assert "as far down" in note
    assert "activity level" in note
    # Nothing moved his target -- it sits on the formula's floor -- so it must not say so.
    assert "already moved" not in note
    # Unexplained weight change can be a medical signal, not only a profile typo.
    assert "clinician" in note


def test_the_note_is_plain_when_on_track():
    note = trend_note(MAN, "maintain", None, 0.0, weekly(65.0, 65.1, 65.0), stepped_on=None)
    assert "tracking your goal" in note
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_recalibration.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'app.nutrition_core.recalibration'`

- [ ] **Step 3: Write the module**

Create `app/nutrition_core/recalibration.py`:

```python
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
```

Then floor the loss target itself. In `app/nutrition_core/energy.py`, add below `PACE_KG_PER_WEEK`:

```python
# The conventional floor for calorie restriction without medical supervision.
SAFE_FLOOR_KCAL = {"female": 1200.0, "male": 1500.0}
```

and replace the `lose` branch of `energy_target` with:

```python
    if goal == "lose":
        # Never below BMR, and never below the safe floor -- unless maintenance itself
        # is lower, since a loss goal must never ask for more than maintenance.
        floor = max(basal_metabolic_rate(body), min(maintenance, SAFE_FLOOR_KCAL[body.sex]))
        return max(maintenance - daily_change, floor)
```

Update the `energy_target` docstring's first line to "The daily energy target for a goal, never below BMR or, for a loss, the safe floor." Then append to `tests/test_energy.py`, importing `total_energy_expenditure` if the file does not already:

```python
def test_a_loss_target_never_falls_below_the_safe_floor():
    """1,200 kcal for women and 1,500 for men is the conventional floor for cutting
    calories without medical supervision. BMR alone sits under it for many smaller
    and older people, so the clamp takes the higher of the two."""
    woman = Body(sex="female", age=65, weight_kg=55.0, activity="sedentary")
    man = Body(sex="male", age=65, weight_kg=65.0, activity="sedentary")

    assert energy_target(woman, goal="lose", pace="steady") == 1200.0
    assert energy_target(man, goal="lose", pace="steady") == 1500.0


def test_a_loss_target_never_asks_for_more_than_maintenance():
    """The floor gives way where maintenance itself is lower (1,404.5 kcal here)."""
    body = Body(sex="male", age=70, weight_kg=45.0, activity="sedentary")

    assert energy_target(body, goal="lose", pace="steady") == pytest.approx(
        total_energy_expenditure(body)
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_recalibration.py tests/test_energy.py tests/test_targets.py -q && uv run ruff check app/nutrition_core tests/test_recalibration.py tests/test_energy.py`
Expected: all PASS (the bounds grid alone is 80 cases), and ruff reports `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add app/nutrition_core/recalibration.py app/nutrition_core/energy.py \
  tests/test_recalibration.py tests/test_energy.py
git commit -m "feat(backend): add the weight-driven recalibration arithmetic

Pure functions for everything the weight feature decides: the smoothed weight,
the least-squares trend over the last four weeks since the last step, the
trajectory the goal's real deficit implies, and a step bounded to 10% of the
formula that never takes the target below BMR or the 1,200/1,500 kcal floor.
The loss target itself is now floored the same way: BMR alone let a 70-year-old
woman at 42 kg be given 1,050 kcal.

The expected rate comes from the energy gap, not the pace's name, because the
BMR clamp shrinks the deficit for small sedentary users; holding a clamped
woman to 0.5 kg/week would read an on-track trend as a stall and push against
a floor that cannot move.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `build_targets` follows the recalibration

The spec says the macros and ICMR's energy-scaled nutrients recompute from the new calorie figure, while protein and every other micronutrient stay put. In code, only fibre was energy-scaled. Thiamine, riboflavin, niacin and B6 are table rows keyed by activity level, so they need an explicit ratio.

**Files:**
- Modify: `app/nutrition_core/targets.py`
- Test: `tests/test_targets.py` (append)

**Interfaces:**
- Consumes: `recalibration.recalibrated_energy` (Task 1)
- Produces:
  - `build_targets(..., upper_limits, *, energy_offset_kcal: float = 0.0) -> dict[str, Target]`
  - `ENERGY_SCALED_REFERENCES: frozenset[str]`
  - `ReferenceValue.source: str | None = None`, used by Task 6. It is added here so the dataclass changes once.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_targets.py`:

```python
"""
A weight-driven recalibration moves the energy target, and with it everything
ICMR derives from energy: the macros, fibre, and the four B vitamins stored per
activity level. It must not move protein, which is per kilogram of the weight
the body actually has, nor the RDA-anchored micronutrients.
"""


def recalibrated(offset: float, body: Body = MAN):
    return build_targets(
        body,
        goal="maintain",
        pace=None,
        cereal_dominant=False,
        references=REFERENCES,
        upper_limits=UPPER_LIMITS,
        energy_offset_kcal=offset,
    )


def test_without_an_offset_every_target_is_exactly_what_it_was():
    assert recalibrated(0.0) == targets_for(MAN)


def test_an_offset_moves_the_energy_target():
    formula = targets_for(MAN)["energy"].rda
    assert recalibrated(-200.0)["energy"].rda == pytest.approx(formula - 200.0)


def test_the_macros_and_fibre_follow_the_recalibrated_energy():
    moved = recalibrated(-200.0)
    energy = moved["energy"].rda

    assert moved["fibre"].rda == pytest.approx(energy / 2000.0 * 30.0)
    assert moved["fat"].rda == pytest.approx(energy * 0.25 / 9.0)
    assert moved["saturated_fat"].rda == pytest.approx(energy * 0.10 / 9.0)


def test_the_energy_scaled_b_vitamins_follow_it_by_the_same_ratio():
    base, moved = targets_for(MAN), recalibrated(-200.0)
    ratio = moved["energy"].rda / base["energy"].rda

    assert moved["thiamine"].rda == pytest.approx(1.4 * ratio)
    assert moved["thiamine"].ear == pytest.approx(1.2 * ratio)


def test_protein_and_the_rda_anchored_micronutrients_do_not_move():
    base, moved = targets_for(MAN), recalibrated(-200.0)

    assert moved["protein"] == base["protein"]
    assert moved["calcium"] == base["calcium"]
    assert moved["iron"] == base["iron"]
    assert moved["vitamin_b12"] == base["vitamin_b12"]


def test_an_offset_beyond_the_bound_is_held_to_ten_percent():
    formula = targets_for(MAN)["energy"].rda
    assert recalibrated(-900.0)["energy"].rda == pytest.approx(formula * 0.9)


def test_a_reference_row_carries_its_source():
    assert ReferenceValue(ear=5, rda=8, ai=None, source="IOM").source == "IOM"
    assert ReferenceValue(ear=5, rda=8, ai=None).source is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_targets.py -q`
Expected: FAIL: `TypeError: build_targets() got an unexpected keyword argument 'energy_offset_kcal'`, and `TypeError: ReferenceValue.__init__() got an unexpected keyword argument 'source'`

- [ ] **Step 3: Implement**

In `app/nutrition_core/targets.py`, replace the energy import with:

```python
from app.nutrition_core.energy import Body, energy_target
from app.nutrition_core.recalibration import recalibrated_energy
```

Below `CEILING_NUTRIENTS`, add:

```python
# Energy-scaled by ICMR's own method, and stored per activity level. When a
# weight-driven recalibration moves the calorie target these move with it, by the
# same ratio; with no recalibration the ratio is exactly 1.
ENERGY_SCALED_REFERENCES = frozenset({"thiamine", "riboflavin", "niacin", "vitamin_b6"})
```

Give `ReferenceValue` a source:

```python
@dataclass(frozen=True)
class ReferenceValue:
    """One resolved `rda_reference` row: already filtered by sex, age and activity."""

    ear: float | None
    rda: float | None
    ai: float | None
    # The framework the row comes from ("ICMR-NIN-2020", "IOM", ...). Carried so a
    # target taken from outside ICMR can say so rather than pass as ICMR's.
    source: str | None = None
```

Change the signature and the first line of `build_targets`:

```python
def build_targets(
    body: Body,
    goal: str,
    pace: str | None,
    cereal_dominant: bool,
    references: dict[str, ReferenceValue],
    upper_limits: dict[str, float],
    *,
    energy_offset_kcal: float = 0.0,
) -> dict[str, Target]:
    """Base targets, before any condition overlay or ledger adjustment.

    `energy_offset_kcal` is the weight-driven recalibration in force, if any. It
    moves the energy target -- bounded and floored in `recalibrated_energy` -- and
    through it the macros, fibre and the energy-scaled B vitamins. Protein does
    not follow it: protein is per kilogram of the weight the body actually has.
    """
    formula = energy_target(body, goal=goal, pace=pace)
    energy = recalibrated_energy(body, formula, energy_offset_kcal)
    energy_scale = energy / formula
```

Replace the last line of the reference loop (`targets[code] = make(code, figure, ear=reference.ear)`) with:

```python
        ear = reference.ear
        if code in ENERGY_SCALED_REFERENCES:
            figure *= energy_scale
            ear = ear * energy_scale if ear is not None else None

        targets[code] = make(code, figure, ear=ear)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_targets.py tests/test_conditions.py tests/test_recalibration.py -q`
Expected: all PASS. The existing tests are unchanged because an offset of 0 gives a ratio of exactly 1.

- [ ] **Step 5: Commit**

```bash
git add app/nutrition_core/targets.py tests/test_targets.py
git commit -m "feat(backend): let a recalibration move energy and what ICMR scales with it

build_targets takes the offset in force and applies it through
recalibrated_energy, so the macros and fibre follow as they always followed
energy. Thiamine, riboflavin, niacin and B6 are activity-level table rows
rather than per-kcal figures, so they scale by the same ratio explicitly;
protein and the other micronutrients stay RDA- or weight-anchored, as the
spec requires.

With no offset the ratio is exactly 1 and every existing target is unchanged.
ReferenceValue gains the row's source for the postmenopausal iron note.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Models and migration

Six tables and one column. Each is keyed to the user and cascades with them, and none belongs to the profile's child set.

**Files:**
- Create: `app/models/weight.py`, `app/models/cycle.py`, `alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py`
- Modify:
  - `app/models/profile.py`: the `menstrual_status` column
  - `app/models/__init__.py`
  - `scripts/e2e_session.py`: `OWNED_MODELS`
- Test: `tests/test_weight_cycle_models.py` (create)

**Interfaces (produced):**
```python
WeightLog(user_id, logged_on: date, weight_kg: float)                   # uq (user_id, logged_on)
CalorieAdjustment(user_id, effective_from: date, kind: str,             # kind: step | reset
                  offset_kcal: float, expected_kg_per_week: float | None,
                  observed_kg_per_week: float | None, reason: str)      # uq (user_id, effective_from)
CycleSettings(user_id, enabled: bool)                                   # uq (user_id)
CycleLog(user_id, logged_on: date, flow: str)                           # uq (user_id, logged_on)
CycleSymptom(user_id, logged_on: date, symptom: str)                    # uq (user_id, logged_on, symptom)
CycleScreening(user_id, answered_on: date, soaks_within_two_hours: bool,
               longer_than_seven_days: bool, large_clots: bool, flooding: bool)  # uq (user_id, answered_on)
Profile.menstrual_status: str | None                                    # menstruating | postmenopausal
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weight_cycle_models.py`:

```python
"""Where a day is the unit, the database holds one row per day.

Two weigh-ins an hour apart are the same measurement, and two cycle logs for
one date would double a bleed's length -- which is exactly what the >7-day
referral counts. The service upserts; these constraints are the backstop.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.user import User
from app.models.weight import CalorieAdjustment, WeightLog

DAY = datetime.date(2026, 8, 17)


@pytest.fixture
def user(db) -> User:
    user = User(google_sub="sub-models", email="models@example.com", name="Models")
    db.add(user)
    db.flush()
    return user


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_weigh_in_per_day(db, user):
    db.add(WeightLog(user_id=user.id, logged_on=DAY, weight_kg=70.0))
    db.flush()
    refused(db, WeightLog(user_id=user.id, logged_on=DAY, weight_kg=70.4))


def test_one_calorie_adjustment_per_day(db, user):
    db.add(
        CalorieAdjustment(
            user_id=user.id, effective_from=DAY, kind="step", offset_kcal=-210.0, reason="x"
        )
    )
    db.flush()
    refused(
        db,
        CalorieAdjustment(
            user_id=user.id, effective_from=DAY, kind="reset", offset_kcal=0.0, reason="y"
        ),
    )


def test_one_cycle_settings_row_per_user(db, user):
    db.add(CycleSettings(user_id=user.id, enabled=True))
    db.flush()
    refused(db, CycleSettings(user_id=user.id, enabled=False))


def test_cycle_tracking_is_off_by_default(db, user):
    settings = CycleSettings(user_id=user.id)
    db.add(settings)
    db.flush()
    assert settings.enabled is False


def test_one_flow_per_day(db, user):
    db.add(CycleLog(user_id=user.id, logged_on=DAY, flow="medium"))
    db.flush()
    refused(db, CycleLog(user_id=user.id, logged_on=DAY, flow="heavy"))


def test_a_day_holds_several_symptoms_but_each_once(db, user):
    db.add_all(
        [
            CycleSymptom(user_id=user.id, logged_on=DAY, symptom="cramps"),
            CycleSymptom(user_id=user.id, logged_on=DAY, symptom="bloating"),
        ]
    )
    db.flush()
    refused(db, CycleSymptom(user_id=user.id, logged_on=DAY, symptom="cramps"))


def test_one_set_of_screening_answers_per_day(db, user):
    db.add(CycleScreening(user_id=user.id, answered_on=DAY))
    db.flush()
    refused(db, CycleScreening(user_id=user.id, answered_on=DAY, flooding=True))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_weight_cycle_models.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'app.models.cycle'`

- [ ] **Step 3: Write the models**

Create `app/models/weight.py`:

```python
import datetime
import uuid

from sqlalchemy import Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class WeightLog(TimestampedBase):
    """One weigh-in, on the user's local date.

    One per day: a second weigh-in the same morning replaces the first rather
    than sitting beside it, since two readings an hour apart are one measurement
    and would count twice in the trend. The newest weigh-in is also the profile's
    weight -- see `app/weight/service.py`.
    """

    __tablename__ = "weight_logs"
    __table_args__ = (UniqueConstraint("user_id", "logged_on", name="uq_weight_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    weight_kg: Mapped[float] = mapped_column(Float)


class CalorieAdjustment(TimestampedBase):
    """A recalibration of the calorie target, in force from `effective_from` on.

    Holds the total offset from the energy formula, not a calorie figure: the
    formula is re-evaluated at the current weight every day, and the offset
    corrects only what the formula misses. Stored rather than derived, because a
    step depends on the goal in force when it was taken, and there is no history
    of goals to replay it against.

    The row in force on a date is the latest whose `effective_from` is on or
    before it, so a past day keeps the target it had. A `reset` row (offset 0)
    marks a goal change: it returns the target to the formula and restarts the
    trend window.
    """

    __tablename__ = "calorie_adjustments"
    __table_args__ = (
        UniqueConstraint("user_id", "effective_from", name="uq_adjustment_user_day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    effective_from: Mapped[datetime.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8))  # step | reset
    offset_kcal: Mapped[float] = mapped_column(Float)
    # The trend a step was read from. Null on a reset, which reads none.
    expected_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
```

Create `app/models/cycle.py`:

```python
import datetime
import uuid

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class CycleSettings(TimestampedBase):
    """Whether cycle tracking is on. Off unless the user turns it on.

    Its own table rather than a profile column: a profile save replaces the whole
    questionnaire, and a switch set on the Cycle screen has no business being
    reset by an edit to someone's meal times.
    """

    __tablename__ = "cycle_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_cycle_settings_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CycleLog(TimestampedBase):
    """A day of bleeding, with its flow.

    A logged day is a fact, not a prediction. Only 13% of cycles are 28 days, so
    nothing here projects a phase forward; coaching that depends on "days 1-3"
    counts from these rows.
    """

    __tablename__ = "cycle_logs"
    __table_args__ = (UniqueConstraint("user_id", "logged_on", name="uq_cycle_log_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    flow: Mapped[str] = mapped_column(String(8))  # light | medium | heavy


class CycleSymptom(TimestampedBase):
    """A symptom on a day, logged with or without bleeding -- PMS comes before it."""

    __tablename__ = "cycle_symptoms"
    __table_args__ = (
        UniqueConstraint("user_id", "logged_on", "symptom", name="uq_cycle_symptom_user_day"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    logged_on: Mapped[datetime.date] = mapped_column(Date)
    # cramps | bloating | breast_tenderness | low_mood -- the ones the coaching answers.
    symptom: Mapped[str] = mapped_column(String(24))


class CycleScreening(TimestampedBase):
    """Answers to the heavy-bleeding screening questions, as of one day.

    Any yes produces a clinician referral and never a nutrient change: about one
    in five adolescents with heavy bleeding has an underlying bleeding disorder,
    and a dietary answer would suppress that signal.
    """

    __tablename__ = "cycle_screenings"
    __table_args__ = (UniqueConstraint("user_id", "answered_on", name="uq_screening_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    answered_on: Mapped[datetime.date] = mapped_column(Date)
    soaks_within_two_hours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    longer_than_seven_days: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    large_clots: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flooding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

In `app/models/profile.py`, add to `Profile` after `cereal_dominant`:

```python
    # menstruating | postmenopausal. Null for men, and for a woman's profile saved
    # before the question existed, which the targets read as "not postmenopausal".
    # ICMR publishes no postmenopausal iron figure; this is what selects the IOM one.
    menstrual_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

In `app/models/__init__.py`, add these imports:

```python
from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
```

after the `app.models.base` import, and

```python
from app.models.weight import CalorieAdjustment, WeightLog
```

after the `app.models.user` import. Add `"CalorieAdjustment"`, `"CycleLog"`, `"CycleScreening"`, `"CycleSettings"` and `"CycleSymptom"` to `__all__` between `"Base"` and `"Dish"`. Add `"WeightLog"` at the end, after `"UsualIntakeItem"`.

- [ ] **Step 4: Write the migration**

Create `alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py`:

```python
"""weight and cycle

Six per-user tables and one column.

`weight_logs` holds one weigh-in per day. `calorie_adjustments` holds the offset
from the energy formula that a recalibration step (or a goal-change reset) put in
force from a date: an offset rather than a calorie figure, so the formula can
follow the current weight without the step counting the same change twice.

`cycle_settings`, `cycle_logs`, `cycle_symptoms` and `cycle_screenings` are the
optional cycle feature. Nothing in the targets path reads them: the iron target
already averages menstrual loss, and calories do not move with cycle phase.

`profiles.menstrual_status` is nullable and needs no backfill. A woman's profile
saved before it existed reads as "not postmenopausal", which is what the targets
assumed until now.

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _owned(name: str, *columns: sa.Column, unique: tuple[str, ...], constraint: str) -> None:
    """A per-user table: the model's columns, then id and created_at, then keys."""
    op.create_table(
        name,
        sa.Column("user_id", sa.UUID(), nullable=False),
        *columns,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(*unique, name=constraint),
    )
    op.create_index(op.f(f"ix_{name}_user_id"), name, ["user_id"], unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    _owned(
        "weight_logs",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        unique=("user_id", "logged_on"),
        constraint="uq_weight_user_day",
    )
    _owned(
        "calorie_adjustments",
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("offset_kcal", sa.Float(), nullable=False),
        sa.Column("expected_kg_per_week", sa.Float(), nullable=True),
        sa.Column("observed_kg_per_week", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        unique=("user_id", "effective_from"),
        constraint="uq_adjustment_user_day",
    )
    _owned(
        "cycle_settings",
        sa.Column("enabled", sa.Boolean(), nullable=False),
        unique=("user_id",),
        constraint="uq_cycle_settings_user",
    )
    _owned(
        "cycle_logs",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("flow", sa.String(length=8), nullable=False),
        unique=("user_id", "logged_on"),
        constraint="uq_cycle_log_user_day",
    )
    _owned(
        "cycle_symptoms",
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("symptom", sa.String(length=24), nullable=False),
        unique=("user_id", "logged_on", "symptom"),
        constraint="uq_cycle_symptom_user_day",
    )
    _owned(
        "cycle_screenings",
        sa.Column("answered_on", sa.Date(), nullable=False),
        sa.Column("soaks_within_two_hours", sa.Boolean(), nullable=False),
        sa.Column("longer_than_seven_days", sa.Boolean(), nullable=False),
        sa.Column("large_clots", sa.Boolean(), nullable=False),
        sa.Column("flooding", sa.Boolean(), nullable=False),
        unique=("user_id", "answered_on"),
        constraint="uq_screening_user_day",
    )
    op.add_column("profiles", sa.Column("menstrual_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("profiles", "menstrual_status")
    for name in (
        "cycle_screenings",
        "cycle_symptoms",
        "cycle_logs",
        "cycle_settings",
        "calorie_adjustments",
        "weight_logs",
    ):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
```

Then migrate both databases and check that the models and migration agree:

```bash
uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head
uv run alembic check
```

Expected: `No new upgrade operations detected.` If `check` reports a difference, fix the **migration** to match the model. Then prove the downgrade works and return to head:

```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

- [ ] **Step 5: Reset the new tables in the end-to-end run**

In `scripts/e2e_session.py`, extend the imports:

```python
from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.diary import MealLog, MealSlotSkip
from app.models.plan import MealPlan
```

(keep the existing `app.models.profile` and `app.models.user` imports), add

```python
from app.models.weight import CalorieAdjustment, WeightLog
```

after the `app.models.user` import, and replace `OWNED_MODELS` with:

```python
# Everything the walk writes. Each is keyed on user_id; meal_plan_items goes with
# its plan through the foreign key's ON DELETE CASCADE. Missing a table here means
# a second run starts from the first run's leftovers -- a weigh-in history that
# grows every run, or cycle tracking already switched on.
OWNED_MODELS = (
    MealLog,
    MealSlotSkip,
    MealPlan,
    WeightLog,
    CalorieAdjustment,
    CycleLog,
    CycleSymptom,
    CycleScreening,
    CycleSettings,
    HealthCondition,
    Medication,
    MealSlotTime,
    ObservanceRule,
    AvoidedFood,
    FavouriteIngredient,
    UsualIntakeItem,
    Profile,
)
```

Also change the module docstring's `--reset` sentence to: "`--reset` deletes everything the user has logged, planned and answered, so a run starts from onboarding."

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_weight_cycle_models.py tests/test_tracking_api.py -q && uv run ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add app/models/weight.py app/models/cycle.py app/models/profile.py app/models/__init__.py \
  alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py scripts/e2e_session.py \
  tests/test_weight_cycle_models.py
git commit -m "feat(backend): add the weight and cycle tables

weight_logs and calorie_adjustments carry weigh-ins and the offset from the
energy formula a recalibration put in force from a date; cycle_settings,
cycle_logs, cycle_symptoms and cycle_screenings carry the optional cycle
feature. Where a day is the unit the database holds one row per day: two cycle
logs for one date would lengthen a bleed, which is what the >7-day referral
counts. profiles gains a nullable menstrual_status.

The e2e reset now clears every table the walk writes, including meal_plans,
which it had been missing since plan 6.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
## Task 4: The weight service, and `resolve_day` following it

This task stores weigh-ins and steps and makes the targets read them. It adds no HTTP yet: the service is tested against the database directly, and Task 5 puts the router in front of it.

**Files:**
- Create: `app/local_time.py`, `app/weight/__init__.py` (empty), `app/weight/service.py`
- Modify:
  - `app/planner/service.py`: `local_today` moves out
  - `app/profiles/router.py`: `_today_for` becomes `local_today`
  - `app/profiles/service.py`: `body_of`
  - `app/targets/service.py`: offset, energy floor, warning
  - `app/nutrition_core/conditions.py`: the `Warning.kind` comment
- Test: `tests/test_local_time.py` (create), `tests/test_weight_service.py` (create)

**Interfaces:**
- Consumes: Task 1 (`recalibration.*`), Task 2 (`build_targets(..., energy_offset_kcal=)`), Task 3 (`WeightLog`, `CalorieAdjustment`)
- Produces:
```python
# app/local_time.py
def local_today(user: User) -> datetime.date            # the user's date; UTC if their zone is bad

# app/profiles/service.py
def body_of(profile: Profile) -> Body

# app/weight/service.py  -- must never import app.targets.service
class NoProfile(LookupError)
@dataclass(frozen=True) class AdjustmentView: delta_kcal: float; since: date; reason: str
@dataclass(frozen=True) class Trend:
    weigh_ins: list[WeighIn]; smoothed_kg: float | None; goal: str
    expected_kg_per_week: float; observed_kg_per_week: float | None
    calorie_target_kcal: float; adjustment: AdjustmentView | None; note: str | None
def weigh_ins(db, user, until: date | None = None) -> list[WeighIn]      # oldest first
def latest_weight(db, user) -> float | None
def adjustment_on(db, user, on_date) -> CalorieAdjustment | None
def offset_on(db, user, on_date) -> float
def record_weigh_in(db, user, on_date, weight_kg) -> CalorieAdjustment | None   # a step, only for today's
def remove_weigh_in(db, user, on_date) -> bool
def reset_adjustment(db, user, on_date) -> None
def trend(db, user, today) -> Trend

# app/targets/service.py
# DayTargets.warnings may now include kind "calorie-recalibrated"
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_local_time.py`:

```python
"""A user's today is their date, not the server's -- and a garbage zone does not break it."""

import datetime
import zoneinfo

from app.local_time import local_today
from app.models.user import User


def test_today_is_the_date_where_the_user_is():
    user = User(google_sub="s", email="e@example.com", name="n", timezone="Asia/Kolkata")
    assert local_today(user) == datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()


def test_an_unknown_timezone_falls_back_to_utc():
    user = User(google_sub="s", email="e@example.com", name="n", timezone="Not/AZone")
    assert local_today(user) == datetime.datetime.now(datetime.UTC).date()
```

Create `tests/test_weight_service.py`:

```python
"""Weigh-ins, the steps they cause, and how `resolve_day` follows them.

Dates run relative to the real today. From Task 5 on, a profile save records a
weigh-in dated today, so a weigh-in on a fixed date in August would be back-dated
-- and a back-dated weigh-in, by design, moves nothing.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.user import User
from app.nutrition_core.energy import Body, basal_metabolic_rate, energy_target
from app.profiles import service as profiles
from app.targets import service as targets
from app.weight import service as weight
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


def nutrient(resolved, code: str):
    return next(n for n in resolved.nutrients if n.code == code)


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return db.scalar(select(User).where(User.email == "track@example.com"))


def gain_half_a_kilo_a_week(db, user):
    """Two weeks of steady gain on a maintain goal: a trend that calls for a step."""
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    weight.record_weigh_in(db, user, days_ago(7), 65.5)
    return weight.record_weigh_in(db, user, TODAY, 66.0)


def test_a_weigh_in_becomes_the_profile_weight(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    assert profiles.get_profile(db, user).weight_kg == 64.2


def test_a_second_weigh_in_the_same_day_replaces_the_first(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    weight.record_weigh_in(db, user, TODAY, 64.6)
    assert [w.weight_kg for w in weight.weigh_ins(db, user) if w.date == TODAY] == [64.6]


def test_a_back_dated_weigh_in_leaves_the_profile_on_the_newest(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    weight.record_weigh_in(db, user, days_ago(7), 66.0)
    assert profiles.get_profile(db, user).weight_kg == 64.2


def test_a_sustained_gain_on_maintain_takes_a_step_down(db, user):
    step = gain_half_a_kilo_a_week(db, user)

    assert step is not None
    assert step.kind == "step"
    assert step.offset_kcal == -210.0
    assert weight.offset_on(db, user, TODAY) == -210.0


def test_the_step_starts_on_the_day_it_was_taken(db, user):
    gain_half_a_kilo_a_week(db, user)
    # Yesterday keeps the target it had, so its ledger is not re-costed.
    assert weight.offset_on(db, user, days_ago(1)) == 0.0


def test_a_back_dated_weigh_in_takes_no_step(db, user):
    weight.record_weigh_in(db, user, TODAY, 66.0)
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    assert weight.record_weigh_in(db, user, days_ago(7), 65.5) is None
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_resolve_day_follows_the_step(db, user):
    gain_half_a_kilo_a_week(db, user)
    # The formula re-evaluates at the new 66 kg; the step sits on top of it.
    formula = energy_target(
        Body(sex="male", age=25, weight_kg=66.0, activity="sedentary"), goal="maintain", pace=None
    )

    resolved = targets.resolve_day(db, user, TODAY)

    assert nutrient(resolved, "energy").rda == pytest.approx(formula - 210.0)
    # Thiamine is energy-scaled, stored per activity level: 1.4 mg sedentary.
    assert nutrient(resolved, "thiamine").rda == pytest.approx(1.4 * (formula - 210.0) / formula)


def test_today_says_the_target_was_recalibrated(db, user):
    gain_half_a_kilo_a_week(db, user)
    warnings = targets.resolve_day(db, user, TODAY).warnings

    recalibrated = [w for w in warnings if w.kind == "calorie-recalibrated"]
    assert len(recalibrated) == 1
    assert "210 kcal lower" in recalibrated[0].message


def test_there_is_no_recalibration_note_without_a_step(db, user):
    kinds = [w.kind for w in targets.resolve_day(db, user, TODAY).warnings]
    assert "calorie-recalibrated" not in kinds


def test_protein_follows_the_measured_weight(db, user):
    weight.record_weigh_in(db, user, TODAY, 70.0)
    assert nutrient(targets.resolve_day(db, user, TODAY), "protein").rda == pytest.approx(58.1)


def test_removing_a_weigh_in_removes_the_step_it_caused(db, user):
    gain_half_a_kilo_a_week(db, user)

    assert weight.remove_weigh_in(db, user, TODAY)
    assert weight.offset_on(db, user, TODAY) == 0.0
    assert profiles.get_profile(db, user).weight_kg == 65.5


def test_removing_a_missing_weigh_in_reports_it(db, user):
    assert weight.remove_weigh_in(db, user, days_ago(3)) is False


def test_correcting_todays_weigh_in_re_reads_the_trend(db, user):
    gain_half_a_kilo_a_week(db, user)
    # It was 65.3, not 66.0: 0.15 kg/week is inside the tolerance.
    assert weight.record_weigh_in(db, user, TODAY, 65.3) is None
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_filling_in_a_missed_week_takes_no_step(db, user):
    weight.remove_weigh_in(db, user, TODAY)  # the onboarding weigh-in, from Task 5 on
    weight.record_weigh_in(db, user, days_ago(21), 65.0)
    weight.record_weigh_in(db, user, days_ago(14), 65.5)
    # The newest weigh-in, but dated a week ago: a step from then would re-cost
    # six finished days. It fills history, and today's weigh-in will read it.
    assert weight.record_weigh_in(db, user, days_ago(7), 66.0) is None
    assert weight.offset_on(db, user, days_ago(1)) == 0.0


def post_a_typo_behind_a_step(db, user):
    """56.0 was meant as 66.0: the typo alone reads as 5 kg/week of gain."""
    weight.record_weigh_in(db, user, days_ago(14), 56.0)
    weight.record_weigh_in(db, user, days_ago(7), 66.1)
    assert weight.record_weigh_in(db, user, TODAY, 66.0).offset_kcal == -210.0


def test_correcting_the_typo_a_step_was_read_from_removes_it(db, user):
    post_a_typo_behind_a_step(db, user)
    assert weight.record_weigh_in(db, user, days_ago(14), 66.0) is None  # a flat trend
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_removing_the_typo_a_step_was_read_from_removes_it(db, user):
    post_a_typo_behind_a_step(db, user)
    assert weight.remove_weigh_in(db, user, days_ago(14))  # two left: not a trend
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_a_new_weigh_in_outside_the_steps_reading_leaves_it(db, user):
    gain_half_a_kilo_a_week(db, user)
    weight.record_weigh_in(db, user, days_ago(35), 64.0)
    assert weight.offset_on(db, user, TODAY) == -210.0


def test_a_reset_returns_the_target_to_the_formula(db, user):
    gain_half_a_kilo_a_week(db, user)
    weight.reset_adjustment(db, user, TODAY)
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_the_trend_view_reports_the_step(db, user):
    gain_half_a_kilo_a_week(db, user)
    view = weight.trend(db, user, TODAY)

    assert view.adjustment.delta_kcal == pytest.approx(-210.0)
    assert view.adjustment.since == TODAY
    assert view.observed_kg_per_week is None  # the trend restarts at the step
    assert "last moved" in view.note


def test_the_ledger_never_takes_energy_below_the_floor(db, user, signed_in, reference_data):
    # 4,500 kcal of rice yesterday is a 2,400 kcal surplus. Unfloored, the ledger
    # would lower today by 30% of the target to ~1,474 kcal -- under his BMR.
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(days_ago(1)), "slot": "lunch", "food_id": str(reference_data.id),
            "food_kind": "dish", "grams": 3000, "is_estimated": False,
        },
    )
    energy = nutrient(targets.resolve_day(db, user, TODAY), "energy")

    body = Body(sex="male", age=25, weight_kg=65.0, activity="sedentary")
    assert energy.target_effective == pytest.approx(basal_metabolic_rate(body))
    # The ledger still lowered it -- to the floor, not past it.
    assert energy.carried_in < 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_local_time.py tests/test_weight_service.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'app.local_time'` (and `app.weight`)

- [ ] **Step 3: One helper for the user's date**

Create `app/local_time.py`:

```python
"""The user's calendar date. A day boundary is theirs, not the server's."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


def local_today(user: User) -> datetime.date:
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown name, or one malformed enough to be rejected outright. A bad
        # stored timezone should not break the request; UTC is a defensible last
        # resort, and clients pass dates explicitly for most reads anyway.
        zone = ZoneInfo("UTC")
    return datetime.datetime.now(tz=zone).date()
```

In `app/planner/service.py`:
- delete `import zoneinfo`;
- delete the `local_today` function (the three lines after `week_start_for`);
- add `from app.local_time import local_today` after the `app.households` import.

Its callers inside the module are unchanged.

In `app/profiles/router.py`:
- delete `from zoneinfo import ZoneInfo, ZoneInfoNotFoundError` and the `_today_for` function;
- add `from app.local_time import local_today` after the `app.db` import;
- in `read_baseline`, replace `date or _today_for(user)` with `date or local_today(user)`.

- [ ] **Step 4: `body_of` on the profile service**

In `app/profiles/service.py`, add the import `from app.nutrition_core.energy import Body` (after the `app.models.user` import), and add below `get_profile`:

```python
def body_of(profile: Profile) -> Body:
    """The body the energy equations and protein are computed for."""
    return Body(
        sex=profile.sex,
        age=profile.age,
        weight_kg=profile.weight_kg,
        activity=profile.activity,
    )
```

- [ ] **Step 5: Write the weight service**

Create `app/weight/__init__.py` (empty) and `app/weight/service.py`:

```python
"""Weigh-ins, and the calorie recalibration they drive.

The profile's weight is the latest weigh-in. One number rather than two means
protein and the energy formula follow measured weight, as the spec asks, and the
trend starts from the onboarding weight rather than from nothing. Writes go
straight to the profile row -- never through `profiles.save_profile`, which
replaces the whole questionnaire.

Must not import `app.targets.service`: that module reads the offset from here.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.local_time import local_today
from app.models.profile import Profile
from app.models.user import User
from app.models.weight import CalorieAdjustment, WeightLog
from app.nutrition_core import recalibration
from app.nutrition_core.energy import energy_target
from app.profiles import service as profiles

# How much history the weight screen shows. The trend itself reads four weeks.
HISTORY_DAYS = 365

RESET_REASON = (
    "Your goal or activity level changed, so your calorie target starts again from the "
    "formula."
)


class NoProfile(LookupError):
    """No profile, so no weight and no target to speak of."""


@dataclass(frozen=True)
class AdjustmentView:
    delta_kcal: float
    since: datetime.date
    reason: str


@dataclass(frozen=True)
class Trend:
    weigh_ins: list[recalibration.WeighIn]
    smoothed_kg: float | None
    goal: str
    expected_kg_per_week: float
    observed_kg_per_week: float | None
    calorie_target_kcal: float
    # The adjustment in force, when it actually moves today's target.
    adjustment: AdjustmentView | None
    note: str | None


def weigh_ins(
    db: Session, user: User, until: datetime.date | None = None
) -> list[recalibration.WeighIn]:
    """The user's weigh-ins, oldest first."""
    query = select(WeightLog).where(WeightLog.user_id == user.id)
    if until is not None:
        query = query.where(WeightLog.logged_on <= until)
    return [
        recalibration.WeighIn(row.logged_on, row.weight_kg)
        for row in db.scalars(query.order_by(WeightLog.logged_on))
    ]


def latest_weight(db: Session, user: User) -> float | None:
    row = _latest(db, user)
    return row.weight_kg if row is not None else None


def adjustment_on(db: Session, user: User, on_date: datetime.date) -> CalorieAdjustment | None:
    """The adjustment in force on a date: the latest that started on or before it."""
    return db.scalars(
        select(CalorieAdjustment)
        .where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from <= on_date,
        )
        .order_by(CalorieAdjustment.effective_from.desc())
        .limit(1)
    ).first()


def offset_on(db: Session, user: User, on_date: datetime.date) -> float:
    """The kcal offset from the formula in force on a date; 0 when none is."""
    adjustment = adjustment_on(db, user, on_date)
    return adjustment.offset_kcal if adjustment is not None else 0.0


def record_weigh_in(
    db: Session, user: User, on_date: datetime.date, weight_kg: float
) -> CalorieAdjustment | None:
    """Store a weigh-in, and take a recalibration step if the trend now calls for one.

    Returns the step taken, or None. Only a weigh-in dated today that is also the
    newest reads the trend: a step dated earlier would change the target of days
    already over. A weigh-in dated before today fills in history and takes no step
    of its own -- but correcting one the step in force was read from re-reads that
    step, so a typo cannot leave a cut standing.
    """
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile

    existing = _on(db, user, on_date)
    if existing is None:
        db.add(WeightLog(user_id=user.id, logged_on=on_date, weight_kg=weight_kg))
    else:
        existing.weight_kg = weight_kg
    db.flush()

    latest = _latest(db, user)
    profile.weight_kg = latest.weight_kg
    db.flush()

    if latest.logged_on == on_date and on_date == local_today(user):
        # A step already taken today on an earlier figure gives way to this one.
        _drop_step_on(db, user, on_date)
        return _take_step(db, user, profile, on_date)
    if existing is not None:
        _reread_step(db, user, profile, on_date)
    return None


def remove_weigh_in(db: Session, user: User, on_date: datetime.date) -> bool:
    """Delete a weigh-in, and any step taken on the strength of it. False if none."""
    row = _on(db, user, on_date)
    if row is None:
        return False
    db.delete(row)
    _drop_step_on(db, user, on_date)
    db.flush()

    latest = _latest(db, user)
    profile = profiles.get_profile(db, user)
    if profile is not None:
        if latest is not None:
            profile.weight_kg = latest.weight_kg
            db.flush()
        _reread_step(db, user, profile, on_date)
    return True


def reset_adjustment(db: Session, user: User, on_date: datetime.date) -> None:
    """Return the target to the formula from `on_date`, and restart the trend there.

    Weigh-ins from before a goal change were eaten against the old goal, so they
    say nothing about the new one.
    """
    _set(db, user, on_date, kind="reset", offset_kcal=0.0, reason=RESET_REASON)


def trend(db: Session, user: User, today: datetime.date) -> Trend:
    """Everything the weight screen shows, as of the user's today."""
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile

    body = profiles.body_of(profile)
    start = today - datetime.timedelta(days=HISTORY_DAYS)
    history = [w for w in weigh_ins(db, user, until=today) if w.date > start]

    current = adjustment_on(db, user, today)
    offset = current.offset_kcal if current is not None else 0.0
    since = current.effective_from if current is not None else None
    points = recalibration.trend_points(history, as_of=today, since=since)

    formula = energy_target(body, goal=profile.goal, pace=profile.pace)
    target = recalibration.recalibrated_energy(body, formula, offset)

    adjustment = None
    if current is not None and abs(target - formula) >= 1.0:
        adjustment = AdjustmentView(
            delta_kcal=target - formula, since=current.effective_from, reason=current.reason
        )
    stepped_on = since if current is not None and current.kind == "step" else None

    return Trend(
        weigh_ins=history,
        smoothed_kg=recalibration.smoothed_weight(history),
        goal=profile.goal,
        expected_kg_per_week=recalibration.expected_rate(body, profile.goal, profile.pace),
        observed_kg_per_week=recalibration.observed_rate(points),
        calorie_target_kcal=target,
        adjustment=adjustment,
        note=recalibration.trend_note(
            body, profile.goal, profile.pace, offset, points, stepped_on=stepped_on
        ),
    )


def _on(db: Session, user: User, on_date: datetime.date) -> WeightLog | None:
    return db.scalars(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == on_date)
    ).one_or_none()


def _latest(db: Session, user: User) -> WeightLog | None:
    return db.scalars(
        select(WeightLog)
        .where(WeightLog.user_id == user.id)
        .order_by(WeightLog.logged_on.desc())
        .limit(1)
    ).first()


def _take_step(
    db: Session, user: User, profile: Profile, as_of: datetime.date
) -> CalorieAdjustment | None:
    current = adjustment_on(db, user, as_of)
    points = recalibration.trend_points(
        weigh_ins(db, user, until=as_of),
        as_of=as_of,
        since=current.effective_from if current is not None else None,
    )
    step = recalibration.next_step(
        profiles.body_of(profile),
        profile.goal,
        profile.pace,
        current.offset_kcal if current is not None else 0.0,
        points,
    )
    if step is None:
        return None
    return _set(
        db,
        user,
        as_of,
        kind="step",
        offset_kcal=step.offset_kcal,
        reason=step.reason,
        expected=step.expected_kg_per_week,
        observed=step.observed_kg_per_week,
    )


def _set(
    db: Session,
    user: User,
    effective_from: datetime.date,
    *,
    kind: str,
    offset_kcal: float,
    reason: str,
    expected: float | None = None,
    observed: float | None = None,
) -> CalorieAdjustment:
    """Upsert the adjustment for a date: one per day, the newest decision winning."""
    row = db.scalars(
        select(CalorieAdjustment).where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from == effective_from,
        )
    ).one_or_none()
    if row is None:
        row = CalorieAdjustment(user_id=user.id, effective_from=effective_from)
        db.add(row)
    row.kind = kind
    row.offset_kcal = offset_kcal
    row.reason = reason
    row.expected_kg_per_week = expected
    row.observed_kg_per_week = observed
    db.flush()
    return row


def _reread_step(
    db: Session, user: User, profile: Profile, on_date: datetime.date
) -> CalorieAdjustment | None:
    """Re-read the step in force at its own date, if `on_date` was in its reading.

    A step is read from every weigh-in in its window, not only the one on its date,
    so correcting or deleting any of them must re-read it -- or a typo would leave
    a cut the remaining weigh-ins no longer support.
    """
    step = db.scalars(
        select(CalorieAdjustment)
        .where(CalorieAdjustment.user_id == user.id)
        .order_by(CalorieAdjustment.effective_from.desc())
        .limit(1)
    ).first()
    if step is None or step.kind != "step" or on_date > step.effective_from:
        return None

    previous = adjustment_on(db, user, step.effective_from - datetime.timedelta(days=1))
    start = step.effective_from - datetime.timedelta(days=recalibration.TREND_WINDOW_DAYS)
    if previous is not None:
        start = max(start, previous.effective_from)
    if on_date < start:
        return None

    as_of = step.effective_from
    db.delete(step)
    db.flush()
    return _take_step(db, user, profile, as_of)


def _drop_step_on(db: Session, user: User, on_date: datetime.date) -> None:
    # Only a step: a reset on the same day is a goal change, which still stands.
    db.execute(
        delete(CalorieAdjustment).where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from == on_date,
            CalorieAdjustment.kind == "step",
        )
    )
```

- [ ] **Step 6: Make `resolve_day` follow the offset, and floor the energy ledger**

In `app/targets/service.py`:

1. Replace the import `from app.nutrition_core.energy import Body` with these three imports, keeping them in isort order among the `app.nutrition_core` imports:
   ```python
   from app.nutrition_core.energy import energy_target
   from app.nutrition_core.recalibration import lowest_target
   ```
   and, after `from app.profiles import service as profiles`:
   ```python
   from app.weight import service as weight
   ```

2. Give `_policies` an optional floor per nutrient:

```python
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
```

3. In `resolve_day`, replace everything from `body = Body(` down to and including `policies = _policies(targets, nutrients, overlay.compensation_disabled)` with:

```python
    body = profiles.body_of(profile)
    formula = energy_target(body, goal=profile.goal, pace=profile.pace)
    base = build_targets(
        body,
        goal=profile.goal,
        pace=profile.pace,
        cereal_dominant=profile.cereal_dominant,
        references=load_references(db, profile),
        upper_limits=load_upper_limits(db),
        # The recalibration in force on this date, so a past day keeps the target
        # it had and a step taken today does not re-cost yesterday.
        energy_offset_kcal=weight.offset_on(db, user, target_date),
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
```

4. Replace the final `return` of `resolve_day` with:

```python
    return DayTargets(
        date=target_date,
        nutrients=rows,
        warnings=[
            *overlay.warnings,
            *_recalibration_warnings(targets["energy"].rda - formula),
        ],
        hold_steady=overlay.compensation_disabled,
    )
```

5. Add the helper below `_policies`:

```python
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
```

6. In `app/nutrition_core/conditions.py`, replace the `Warning` dataclass body's comment so the kinds are listed in one place:

```python
@dataclass(frozen=True)
class Warning:
    # condition-conflict | medication-timing | drug-interaction, from the overlay;
    # calorie-recalibrated | reference-framework | approaching-limit, from resolve_day.
    kind: str
    message: str
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_local_time.py tests/test_weight_service.py tests/test_targets_service.py tests/test_tracking_api.py tests/test_planner_api.py -q && uv run ruff check .`
Expected: all PASS, ruff clean. The tracking and planner suites are unchanged: with no weigh-ins the offset is 0, and none of their days has an energy surplus deep enough to reach the floor.

- [ ] **Step 8: Commit**

```bash
git add app/local_time.py app/weight app/planner/service.py app/profiles/router.py \
  app/profiles/service.py app/targets/service.py app/nutrition_core/conditions.py \
  tests/test_local_time.py tests/test_weight_service.py
git commit -m "feat(backend): store weigh-ins and let the targets follow a recalibration

A weigh-in becomes the profile's weight, and when it is today's and the newest
the trend is re-read and a bounded step may be stored as an offset from the
formula, effective from today; correcting or deleting a weigh-in the step was
read from re-reads it, so a typo cannot leave a cut standing. resolve_day reads the offset in force on
each date, so a past day keeps its target and every consumer -- the macros,
the energy-scaled B vitamins, the ledger, Today and the planner -- follows one
figure. A calorie-recalibrated warning says so whenever it has moved.

The energy ledger now respects the same floor. Carries from two surplus days
add up, and without it they could take a day to 40% of its target, far under
BMR, which is the figure the planner sizes portions from.

One local_today helper replaces the planner's and the profile router's, which
disagreed about a bad timezone.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: The weight API, and the profile's part in it

**Files:**
- Create: `app/weight/router.py`
- Modify: `app/main.py`, `app/profiles/router.py` (weigh-in on a weight change, reset on a goal change)
- Test: `tests/test_weight_api.py` (create)

**Interfaces:**
- Consumes: `app.weight.service` (Task 4); `app.planner.service.week_start_for`, in the tests only
- Produces the HTTP contract that Task 9 writes into `frontend/src/weight/types.ts`:

| Method and path | Body | Answer |
|---|---|---|
| `GET /weight` | — | 200 `WeightTrendOut`; 404 with no profile |
| `POST /weight` | `{weight_kg: 20 < x ≤ 300, date?: "YYYY-MM-DD"}` | 201 `WeightTrendOut`; 422 for a future date or an implausible weight; 404 with no profile |
| `DELETE /weight/{date}` | — | 204; 404 when there is no weigh-in on that date |

```
WeightTrendOut {
  weigh_ins: [{date, weight_kg}]
  smoothed_kg: float | null
  goal
  expected_kg_per_week
  observed_kg_per_week: float | null
  calorie_target_kcal: int
  adjustment: {delta_kcal: int, since: date, reason} | null
  note: str | null
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_weight_api.py`:

```python
"""The weight API: weigh-ins in, a trend and the calorie target out.

Dates are relative to the real today, because a profile save records a weigh-in
dated today.
"""

import datetime
import zoneinfo

import pytest

from app.models.user import User
from app.models.weight import WeightLog
from app.planner import service as planner_service
from tests.test_tracking_api import PROFILE, nutrient

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
WEEK = planner_service.week_start_for(TODAY)


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


def take_a_step(api) -> dict:
    """Spec manual step 8 -- drift from the goal moves the target by a bounded step --
    with the third weigh-in a trend needs."""
    api.post("/weight", json={"weight_kg": 65.0, "date": str(days_ago(14))})
    api.post("/weight", json={"weight_kg": 65.5, "date": str(days_ago(7))})
    response = api.post("/weight", json={"weight_kg": 66.0})
    assert response.status_code == 201, response.text
    return response.json()


def test_weight_needs_a_session(api_client):
    assert api_client.get("/weight").status_code == 401


def test_weight_needs_a_profile(signed_in):
    assert signed_in.get("/weight").status_code == 404
    assert signed_in.post("/weight", json={"weight_kg": 70.0}).status_code == 404


def test_onboarding_records_the_first_weigh_in(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = signed_in.get("/weight").json()

    assert trend["weigh_ins"] == [{"date": str(TODAY), "weight_kg": 65.0}]
    assert trend["smoothed_kg"] == 65.0
    assert trend["observed_kg_per_week"] is None
    assert trend["adjustment"] is None
    assert "three weigh-ins" in trend["note"]


def test_saving_the_profile_again_does_not_duplicate_the_weigh_in(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.put("/profile", json=PROFILE)
    assert len(signed_in.get("/weight").json()["weigh_ins"]) == 1


def test_a_weigh_in_defaults_to_today_and_answers_with_the_trend(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    response = signed_in.post("/weight", json={"weight_kg": 64.4})

    assert response.status_code == 201
    assert response.json()["weigh_ins"][-1] == {"date": str(TODAY), "weight_kg": 64.4}


def test_a_weigh_in_moves_the_profile_weight(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/weight", json={"weight_kg": 64.4})
    assert signed_in.get("/profile").json()["weight_kg"] == 64.4


def test_a_weigh_in_cannot_be_dated_in_the_future(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    tomorrow = TODAY + datetime.timedelta(days=1)
    response = signed_in.post("/weight", json={"weight_kg": 64.0, "date": str(tomorrow)})
    assert response.status_code == 422


@pytest.mark.parametrize("kg", [7.4, 20.0, 301.0])
def test_an_implausible_weight_is_refused(signed_in, reference_data, kg):
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.post("/weight", json={"weight_kg": kg}).status_code == 422


def test_the_calorie_target_is_the_same_figure_today_shows(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = signed_in.get("/weight").json()
    energy = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "energy")

    assert trend["calorie_target_kcal"] == round(energy["rda"])
    assert trend["expected_kg_per_week"] == 0.0


def test_sustained_drift_moves_the_target_by_a_bounded_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    before = signed_in.get("/weight").json()["calorie_target_kcal"]

    trend = take_a_step(signed_in)

    assert trend["adjustment"]["delta_kcal"] == -210
    assert trend["adjustment"]["since"] == str(TODAY)
    assert "risen about 0.5 kg a week" in trend["adjustment"]["reason"]
    # The formula rose with the extra kilogram; the step sits on top, inside 10%.
    assert abs(trend["calorie_target_kcal"] - before) < 0.1 * before


def test_today_carries_the_recalibrated_target_and_says_so(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = take_a_step(signed_in)
    today = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert round(nutrient(today, "energy")["rda"]) == trend["calorie_target_kcal"]
    assert "calorie-recalibrated" in [w["kind"] for w in today["warnings"]]


def test_a_weigh_in_can_be_removed(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/weight", json={"weight_kg": 64.0, "date": str(days_ago(7))})

    assert signed_in.delete(f"/weight/{days_ago(7)}").status_code == 204
    dates = [w["date"] for w in signed_in.get("/weight").json()["weigh_ins"]]
    assert dates == [str(TODAY)]


def test_removing_a_missing_weigh_in_is_not_found(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.delete(f"/weight/{days_ago(3)}").status_code == 404


def test_changing_the_goal_resets_the_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    take_a_step(signed_in)

    signed_in.put(
        "/profile", json={**PROFILE, "goal": "lose", "pace": "gentle", "weight_kg": 66.0}
    )

    trend = signed_in.get("/weight").json()
    assert trend["adjustment"] is None
    assert trend["goal"] == "lose"


def test_editing_something_else_keeps_the_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    take_a_step(signed_in)

    signed_in.put("/profile", json={**PROFILE, "weight_kg": 66.0, "conditions": ["prediabetes"]})

    assert signed_in.get("/weight").json()["adjustment"]["delta_kcal"] == -210


def test_a_step_and_its_removal_leave_the_stored_plan_alone(
    signed_in, reference_data, monkeypatch
):
    """Regenerating replaces every unlocked item, and a swap is not a lock: a weigh-in
    must never silently throw away the week the user customised."""
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.get(f"/plan/week?start={WEEK}").status_code == 200
    calls = []
    monkeypatch.setattr(
        planner_service, "generate_week", lambda db, user, start, **kw: calls.append(start)
    )

    assert take_a_step(signed_in)["adjustment"] is not None
    signed_in.delete(f"/weight/{TODAY}")

    assert calls == []


def test_filling_in_a_past_week_takes_no_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.delete(f"/weight/{TODAY}")
    for n, kg in ((21, 65.0), (14, 65.5), (7, 66.0)):
        response = signed_in.post("/weight", json={"weight_kg": kg, "date": str(days_ago(n))})
        assert response.status_code == 201

    assert signed_in.get("/weight").json()["adjustment"] is None


def test_another_users_weigh_ins_are_not_visible(signed_in, reference_data, db):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(WeightLog(user_id=other.id, logged_on=days_ago(2), weight_kg=90.0))
    db.flush()

    signed_in.put("/profile", json=PROFILE)
    assert [w["weight_kg"] for w in signed_in.get("/weight").json()["weigh_ins"]] == [65.0]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_weight_api.py -q`
Expected: FAIL, with `/weight` answering 404 `Not Found` for the routes that do not exist yet.

- [ ] **Step 3: Write the router**

Create `app/weight/router.py`:

```python
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.local_time import local_today
from app.models.user import User
from app.weight import service

router = APIRouter(prefix="/weight", tags=["weight"])


class WeighInIn(BaseModel):
    # The same plausibility bounds as the profile's weight: the energy equations
    # are weight-based, so a typo here would quietly skew every target.
    weight_kg: float = Field(gt=20, le=300)
    # Defaults to the user's today. A date lets a missed week be filled in; only a
    # weigh-in dated today re-reads the trend.
    date: datetime.date | None = None


class WeighInOut(BaseModel):
    date: datetime.date
    weight_kg: float


class AdjustmentOut(BaseModel):
    delta_kcal: int
    since: datetime.date
    reason: str


class WeightTrendOut(BaseModel):
    weigh_ins: list[WeighInOut]
    smoothed_kg: float | None
    goal: str
    expected_kg_per_week: float
    observed_kg_per_week: float | None
    calorie_target_kcal: int
    adjustment: AdjustmentOut | None
    note: str | None


def _out(trend: service.Trend) -> WeightTrendOut:
    adjustment = None
    if trend.adjustment is not None:
        adjustment = AdjustmentOut(
            delta_kcal=round(trend.adjustment.delta_kcal),
            since=trend.adjustment.since,
            reason=trend.adjustment.reason,
        )
    return WeightTrendOut(
        weigh_ins=[WeighInOut(date=w.date, weight_kg=w.weight_kg) for w in trend.weigh_ins],
        smoothed_kg=round(trend.smoothed_kg, 1) if trend.smoothed_kg is not None else None,
        goal=trend.goal,
        expected_kg_per_week=round(trend.expected_kg_per_week, 2),
        observed_kg_per_week=(
            round(trend.observed_kg_per_week, 2)
            if trend.observed_kg_per_week is not None
            else None
        ),
        calorie_target_kcal=round(trend.calorie_target_kcal),
        adjustment=adjustment,
        note=trend.note,
    )


@router.get("", response_model=WeightTrendOut)
def read_trend(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WeightTrendOut:
    try:
        return _out(service.trend(db, user, local_today(user)))
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


@router.post("", response_model=WeightTrendOut, status_code=status.HTTP_201_CREATED)
def add_weigh_in(
    payload: WeighInIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightTrendOut:
    today = local_today(user)
    on_date = payload.date or today
    if on_date > today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A weigh-in cannot be dated in the future"
        )
    try:
        # A step moves the target but never rewrites a stored plan: regenerating would
        # throw away the user's swaps. Regenerate on the Plan screen re-sizes portions.
        service.record_weigh_in(db, user, on_date, payload.weight_kg)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _out(service.trend(db, user, today))


@router.delete("/{on_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_weigh_in(
    on_date: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not service.remove_weigh_in(db, user, on_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No weigh-in on that date")
    db.commit()
```

In `app/main.py`, add `from app.weight.router import router as weight_router` after the `app.targets.router` import, and `app.include_router(weight_router)` after `app.include_router(planner_router)`.

- [ ] **Step 4: Let a profile save record a weigh-in and reset a step**

In `app/profiles/router.py`, add `from app.weight import service as weight` after the `app.profiles` imports. Add this helper above `save_profile`:

```python
def _energy_basis(goal: str, pace: str | None, activity: str) -> tuple[str, str | None, str]:
    """What the energy formula reads from the profile, besides the body itself.

    A pace left over on a maintain goal changes nothing, so it is not a change.
    """
    return goal, pace if goal != "maintain" else None, activity
```

Then replace the last three lines of `save_profile` (`service.save_profile(...)`, `db.commit()`, `return _to_out(db, user)`) with:

```python
    existing = service.get_profile(db, user)
    previous = (
        _energy_basis(existing.goal, existing.pace, existing.activity)
        if existing is not None
        else None
    )

    service.save_profile(db, user, payload)

    today = local_today(user)
    # A step was read against the old goal; under a new one it says nothing.
    if previous is not None and previous != _energy_basis(
        payload.goal, payload.pace, payload.activity
    ):
        weight.reset_adjustment(db, user, today)
    # The profile's weight is the latest weigh-in, so a changed weight is a weigh-in.
    # That is also how onboarding records the first one the trend starts from.
    if weight.latest_weight(db, user) != payload.weight_kg:
        weight.record_weigh_in(db, user, today, payload.weight_kg)

    db.commit()
    return _to_out(db, user)
```

The previous basis has to be read before `save_profile` runs, because that function updates the same row in place.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_weight_api.py tests/test_weight_service.py tests/test_tracking_api.py tests/test_preferences_api.py tests/test_planner_api.py -q && uv run ruff check .`
Expected: all PASS. The profile and planner suites are unaffected by the weigh-in each save now records: its date is today, and their fixed-date reads are in August.

- [ ] **Step 6: Commit**

```bash
git add app/weight/router.py app/main.py app/profiles/router.py tests/test_weight_api.py
git commit -m "feat(backend): add the weight API, and record the profile's weight as a weigh-in

GET/POST /weight answer with the trend the weight screen draws: the weigh-ins,
the smoothed weight, the trajectory the goal implies and the one observed, the
calorie target (the same figure Today shows), the step in force and a sentence
on where things stand. A weigh-in may be back-dated to fill a missed week but
never future-dated, and DELETE /weight/{date} takes its step with it.

A profile save whose weight differs from the latest weigh-in records one, so
onboarding gives the trend its starting point. A change of goal, pace or
activity resets the step: it was read against a goal that no longer applies.
A step never rewrites a stored plan -- regenerating would throw away the
user's swaps -- so Regenerate on the Plan screen is what re-sizes portions.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Postmenopausal status, and the iron target it selects

**Files:**
- Modify:
  - `app/profiles/router.py`: `menstrual_status` in `ProfileIn`, `ProfileOut` and `_to_out`
  - `app/profiles/service.py`: `menstrual_status` in `fields`
  - `app/targets/service.py`: sources on references, the postmenopausal iron row, two warnings
  - `tests/conftest.py`: the `iron_reference` fixture
- Test: `tests/test_menstrual_status.py` (create)

**Interfaces:**
- Consumes: `ReferenceValue.source` (Task 2), `Profile.menstrual_status` (Task 3)
- Produces:
  - `PUT /profile` and `GET /profile` carry `menstrual_status: "menstruating" | "postmenopausal" | null`. It is always null for a male profile.
  - `DayTargets.warnings` may include `reference-framework` (the iron target is the IOM figure) and `approaching-limit` (postmenopausal iron at 80% or more of its upper limit).

- [ ] **Step 1: Add the iron fixture**

In `tests/conftest.py`, below `reference_data`, add:

```python
@pytest.fixture
def iron_reference(db, reference_data) -> Nutrient:
    """Iron as the seed carries it for women: ICMR's 29 mg up to 59, and the IOM
    figure of 8 mg stored as the female 60+ row -- the value the spec falls back to
    after menopause, since ICMR-NIN 2020 publishes no postmenopausal category."""
    iron = Nutrient(
        code="iron",
        display_name="Iron",
        unit="mg",
        category="mineral",
        is_compensable=True,
        compensation_days=2,
        is_excess_sensitive=True,
    )
    db.add(iron)
    db.flush()
    for sex, band, ear, rda, source in (
        ("female", "18-59", 15, 29, "ICMR-NIN-2020"),
        ("female", "60+", 5, 8, "IOM"),
        ("male", "18-59", 11, 19, "ICMR-NIN-2020"),
    ):
        db.add(
            RdaReference(
                nutrient_id=iron.id,
                sex=sex,
                age_band=band,
                activity_level=None,
                ear=ear,
                rda=rda,
                ai=None,
                source=source,
            )
        )
    db.add(
        UpperLimit(
            nutrient_id=iron.id, value=45.0, supplemental_only=False, source="ICMR-2018-TUL"
        )
    )
    db.flush()
    return iron
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_menstrual_status.py`:

```python
"""Postmenopausal status, and the iron target it selects.

ICMR-NIN 2020 publishes no postmenopausal category. Its 29 mg figure for women
already averages menstrual loss, so applying it to a woman who no longer
menstruates would substantially overstate her requirement -- and there is no
route of iron excretion. The spec falls back to the IOM value, 8 mg, with a
visible note that a different framework is being used.
"""

import datetime

import pytest

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from tests.test_tracking_api import PROFILE, nutrient

TODAY = datetime.date(2026, 8, 17)

WOMAN = {
    **PROFILE,
    "sex": "female",
    "age": 52,
    "weight_kg": 55.0,
    "menstrual_status": "menstruating",
}
POSTMENOPAUSAL = {**WOMAN, "menstrual_status": "postmenopausal"}


@pytest.fixture
def iron_rich_dish(db, iron_reference) -> Dish:
    """40 mg of iron in a 100 g portion: enough for one day to near the 45 mg limit."""
    ingredient = Ingredient(code="test:iron-rich", name="Iron-rich test food", source="IFCT")
    db.add(ingredient)
    db.flush()
    db.add(
        IngredientNutrient(
            ingredient_id=ingredient.id,
            nutrient_id=iron_reference.id,
            per_100g=40.0,
            source="IFCT",
        )
    )
    dish = Dish(
        code="test:iron-dish",
        name="Iron-rich dish",
        source="authored",
        is_editable=True,
        yield_factor=1.0,
    )
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ingredient.id, grams=100.0))
    db.flush()
    return dish


def targets(api) -> dict:
    response = api.get(f"/targets/today?date={TODAY}")
    assert response.status_code == 200, response.text
    return response.json()


def kinds(payload: dict) -> list[str]:
    return [w["kind"] for w in payload["warnings"]]


def test_the_status_reads_back(signed_in):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    assert signed_in.get("/profile").json()["menstrual_status"] == "postmenopausal"


def test_a_mans_profile_never_carries_a_status(signed_in):
    signed_in.put("/profile", json={**PROFILE, "menstrual_status": "menstruating"})
    assert signed_in.get("/profile").json()["menstrual_status"] is None


def test_an_unknown_status_is_refused(signed_in):
    response = signed_in.put("/profile", json={**WOMAN, "menstrual_status": "pregnant"})
    assert response.status_code == 422


def test_a_profile_saved_without_the_field_reads_as_unset(signed_in):
    signed_in.put("/profile", json={**PROFILE, "sex": "female", "weight_kg": 55.0})
    assert signed_in.get("/profile").json()["menstrual_status"] is None


def test_a_menstruating_woman_gets_the_icmr_figure(signed_in, iron_reference):
    signed_in.put("/profile", json=WOMAN)
    payload = targets(signed_in)

    assert nutrient(payload, "iron")["rda"] == 29
    assert "reference-framework" not in kinds(payload)


def test_a_postmenopausal_woman_gets_the_iom_figure(signed_in, iron_reference):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    assert nutrient(targets(signed_in), "iron")["rda"] == 8


def test_the_iom_figure_says_it_is_not_icmrs(signed_in, iron_reference):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    notes = [w for w in targets(signed_in)["warnings"] if w["kind"] == "reference-framework"]

    assert len(notes) == 1
    assert "IOM" in notes[0]["message"]
    assert "8 mg" in notes[0]["message"]


def test_only_iron_changes_band(signed_in, iron_reference):
    # The 60+ band carries four nutrients; switching her whole band would drop the rest.
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    payload = targets(signed_in)

    assert nutrient(payload, "calcium")["rda"] == 1000
    assert nutrient(payload, "thiamine")["rda"] == pytest.approx(1.4)


def test_a_woman_over_sixty_gets_the_note_too(signed_in, iron_reference):
    # Her band already gave her the IOM figure, silently. Now it says so.
    signed_in.put("/profile", json={**WOMAN, "age": 64, "menstrual_status": None})
    payload = targets(signed_in)

    assert nutrient(payload, "iron")["rda"] == 8
    assert "reference-framework" in kinds(payload)


def test_iron_near_the_limit_is_flagged_after_menopause(signed_in, iron_rich_dish):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(iron_rich_dish.id),
            "food_kind": "dish", "grams": 100, "is_estimated": False,
        },
    )
    notes = [w for w in targets(signed_in)["warnings"] if w["kind"] == "approaching-limit"]

    assert len(notes) == 1
    assert "45 mg" in notes[0]["message"]


def test_the_same_day_is_not_flagged_before_menopause(signed_in, iron_rich_dish):
    signed_in.put("/profile", json=WOMAN)
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(iron_rich_dish.id),
            "food_kind": "dish", "grams": 100, "is_estimated": False,
        },
    )
    assert "approaching-limit" not in kinds(targets(signed_in))
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_menstrual_status.py -q`
Expected: FAIL: `KeyError: 'menstrual_status'` from the read-back tests, and iron `rda == 29` where 8 is expected.

- [ ] **Step 4: Carry the field through the profile**

In `app/profiles/router.py`:
- In `ProfileIn`, after `cereal_dominant`, add:
  ```python
      # Selects the iron figure: ICMR's 29 mg averages menstrual loss, so after
      # menopause the IOM figure applies. Ignored -- stored as null -- for a man.
      menstrual_status: str | None = Field(default=None, pattern="^(menstruating|postmenopausal)$")
  ```
- In `ProfileOut`, after `cereal_dominant`, add `menstrual_status: str | None`.
- In `_to_out`, after `cereal_dominant=profile.cereal_dominant,`, add `menstrual_status=profile.menstrual_status,`.

In `app/profiles/service.py`, add to the `fields` dict in `save_profile`:

```python
        # Only a woman's profile carries one. A profile switched to male must not
        # keep a status that would select a female iron row if switched back.
        "menstrual_status": payload.menstrual_status if payload.sex == "female" else None,
```

- [ ] **Step 5: Select the postmenopausal iron row, and say so**

In `app/targets/service.py`, below `COMPENSATION_WINDOW_DAYS`, add:

```python
# ICMR-NIN 2020 publishes no postmenopausal category. The seed stores the IOM
# figure the spec falls back to as the female 60+ iron row, and a postmenopausal
# woman of any age reads that row -- for iron alone. Switching her whole band
# would drop the fourteen nutrients the 60+ band does not carry.
POSTMENOPAUSAL_IRON_BAND = "60+"
IOM_SOURCE = "IOM"

# After menopause there is no route to shed iron, so a day this close to the
# upper limit is worth a word before it becomes a habit.
IRON_LIMIT_SHARE = 0.8
```

Replace the `return` at the end of `load_references` with:

```python
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
```

Add the two warning helpers below `_recalibration_warnings`:

```python
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
```

In `resolve_day`, hold the references in a variable so the warnings can read them:
- Change `references=load_references(db, profile),` in the `build_targets` call to `references=references,`.
- Put `references = load_references(db, profile)` on the line above `base = build_targets(`.

Then change the `warnings=` in the final `return` to:

```python
        warnings=[
            *overlay.warnings,
            *_recalibration_warnings(targets["energy"].rda - formula),
            *_framework_warnings(references),
            *_iron_limit_warnings(references, targets, consumed_today),
        ],
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_menstrual_status.py tests/test_tracking_api.py tests/test_targets_service.py tests/test_weight_service.py tests/test_preferences_api.py -q && uv run ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add app/profiles/router.py app/profiles/service.py app/targets/service.py \
  tests/conftest.py tests/test_menstrual_status.py
git commit -m "feat(backend): add postmenopausal status and the iron fallback it selects

ICMR-NIN 2020 publishes no postmenopausal category, and its 29 mg for women
averages menstrual loss. A profile marked postmenopausal now reads the IOM
figure the seed stores as the female 60+ iron row -- for iron alone, since the
60+ band carries four nutrients and switching it would drop fourteen targets.

Whenever iron is the IOM figure, Today says so, as the spec requires. That
also covers women over 60, who were already on it with no note. After
menopause a day's iron at 80% of the 45 mg limit is flagged, since there is
no route to shed it.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
## Task 7: Cycle rules (pure)

**Files:**
- Create: `app/cycle/__init__.py` (empty), `app/cycle/rules.py`
- Test: `tests/test_cycle_rules.py` (create)

**Interfaces (produced, used by Task 8):**
```python
FLOWS = ("light", "medium", "heavy")
SYMPTOMS = ("cramps", "bloating", "breast_tenderness", "low_mood")
HISTORY_DAYS = 90
@dataclass(frozen=True) class Day: date: date; flow: str | None; symptoms: frozenset[str]
@dataclass(frozen=True) class Screening: answered_on: date; soaks_within_two_hours: bool;
    longer_than_seven_days: bool; large_clots: bool; flooding: bool
@dataclass(frozen=True) class Bleed: start: date; end: date   # .length
@dataclass(frozen=True) class Note: id: str; title: str; body: str; evidence: str
def bleeds(days: Sequence[Day]) -> list[Bleed]                     # oldest first
def last_period_start(days) -> date | None
def bleed_day(days, today) -> int | None                           # 1 on a bleed's first day
def referral_reason(days, screening: Screening | None, today) -> str | None
def coaching(days, today) -> list[Note]
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cycle_rules.py`:

```python
"""What cycle data means: bleeds, referrals and coaching, all from logged days.

Symptom-driven, never calendar-driven. Only 13% of cycles are 28 days and the
follicular phase runs anywhere from 10 to 30, so nothing here predicts a phase;
"day 1-3" is counted from bleeding the user actually logged.
"""

import datetime

from app.cycle.rules import (
    Bleed,
    Day,
    Screening,
    bleed_day,
    bleeds,
    coaching,
    last_period_start,
    referral_reason,
)

TODAY = datetime.date(2026, 8, 17)


def day(offset: int, flow: str | None = None, *symptoms: str) -> Day:
    return Day(TODAY + datetime.timedelta(days=offset), flow, frozenset(symptoms))


def bleed(start: int, length: int, flow: str = "medium") -> list[Day]:
    return [day(start + i, flow) for i in range(length)]


def screening(**answers: bool) -> Screening:
    fields = ("soaks_within_two_hours", "longer_than_seven_days", "large_clots", "flooding")
    return Screening(TODAY, **{field: answers.get(field, False) for field in fields})


def ids(days: list[Day], today: datetime.date = TODAY) -> list[str]:
    return [note.id for note in coaching(days, today)]


# --- bleeds -----------------------------------------------------------------------------------


def test_consecutive_bleeding_days_are_one_bleed():
    one_day = datetime.timedelta(days=1)
    assert bleeds(bleed(0, 5)) == [Bleed(TODAY, TODAY + 4 * one_day)]


def test_a_day_without_bleeding_ends_a_bleed():
    assert len(bleeds([day(0, "light"), day(2, "light")])) == 2


def test_a_symptom_on_its_own_is_not_bleeding():
    assert bleeds([day(0, None, "cramps")]) == []


def test_the_last_period_started_on_the_first_day_of_the_latest_bleed():
    assert last_period_start([*bleed(-30, 5), *bleed(-2, 3)]) == TODAY - datetime.timedelta(days=2)


def test_a_bleed_logged_today_is_on_day_one():
    assert bleed_day(bleed(0, 1), TODAY) == 1


def test_a_bleed_logged_until_yesterday_is_still_current():
    # Today's log may simply not be in yet.
    assert bleed_day(bleed(-2, 2), TODAY) == 3


def test_a_bleed_that_ended_days_ago_is_not_current():
    assert bleed_day(bleed(-5, 3), TODAY) is None


def test_nothing_is_predicted_from_a_period_a_cycle_ago():
    # 28 days after the last period is when a calendar app would say "day 1".
    assert bleed_day(bleed(-28, 5), TODAY) is None


# --- referral ---------------------------------------------------------------------------------


def test_no_referral_without_a_reason():
    assert referral_reason(bleed(-3, 5), None, TODAY) is None


def test_heavy_flow_on_its_own_is_not_a_referral():
    """A self-rated "heavy" is not one of the validated questions. Treating it as
    one would refer most people on their heaviest day and teach them to ignore it."""
    assert referral_reason(bleed(-3, 5, "heavy"), None, TODAY) is None


def test_a_yes_on_the_screening_refers():
    reason = referral_reason([], screening(soaks_within_two_hours=True), TODAY)
    assert "two hours" in reason


def test_every_yes_is_named():
    reason = referral_reason([], screening(large_clots=True, flooding=True), TODAY)
    assert "clots" in reason
    assert "flooding" in reason


def test_all_no_answers_do_not_refer():
    assert referral_reason([], screening(), TODAY) is None


def test_more_than_seven_days_of_bleeding_refers():
    assert "8 days in a row" in referral_reason(bleed(-10, 8), None, TODAY)


def test_seven_days_of_bleeding_does_not():
    assert referral_reason(bleed(-10, 7), None, TODAY) is None


def test_a_long_bleed_months_ago_is_not_raised_again():
    assert referral_reason(bleed(-200, 9), None, TODAY) is None


def test_the_reason_is_whole_sentences():
    # The screen splices it between "Please see a clinician." and its own copy.
    reason = referral_reason(bleed(-10, 8), screening(flooding=True), TODAY)
    assert reason.endswith(".")
    assert reason[0].isupper()


# --- coaching ---------------------------------------------------------------------------------


def test_coffee_timing_and_calcium_always_apply():
    assert ids([]) == ["coffee-timing", "calcium"]


def test_vitamin_c_pairing_follows_a_logged_bleed():
    assert "vitamin-c" in ids(bleed(-3, 3))


def test_vitamin_c_pairing_fades_a_week_after_it():
    assert "vitamin-c" not in ids(bleed(-14, 5))


def test_ginger_and_fenugreek_follow_cramps_on_days_one_to_three():
    days = [day(-1, "medium", "cramps"), day(0, "heavy")]
    assert ids(days) == ["coffee-timing", "vitamin-c", "ginger", "fenugreek", "calcium"]


def test_not_on_day_four():
    days = [day(-3, "medium", "cramps"), day(-2, "heavy"), day(-1, "medium"), day(0, "light")]
    assert "ginger" not in ids(days)


def test_not_without_cramps():
    assert "ginger" not in ids(bleed(-1, 2))


def test_cramps_outside_a_bleed_do_not_bring_ginger():
    assert "ginger" not in ids([day(0, None, "cramps")])


def test_the_calcium_note_names_the_pms_symptoms_logged():
    calcium = coaching([day(-5, None, "bloating", "low_mood")], TODAY)[-1]
    assert "bloating and low mood" in calcium.body


def test_every_note_carries_its_evidence_grade():
    notes = coaching([day(-1, "medium", "cramps"), day(0, "heavy")], TODAY)
    grades = {note.id: note.evidence for note in notes}

    assert grades == {
        "coffee-timing": "strong",
        "vitamin-c": "moderate",
        "ginger": "moderate",
        "fenugreek": "low",
        "calcium": "moderate",
    }


def test_food_is_never_offered_as_a_substitute_for_treatment():
    ginger = next(n for n in coaching([day(0, "heavy", "cramps")], TODAY) if n.id == "ginger")
    assert "ibuprofen" in ginger.body
    assert "not a substitute for treatment" in ginger.body


def test_logged_pms_symptoms_point_to_a_clinician_not_only_to_calcium():
    # Severe PMS and PMDD low mood have effective treatment; calcium is not it.
    calcium = coaching([day(-5, None, "low_mood")], TODAY)[-1]
    assert "clinician" in calcium.body
    assert "not a substitute" in calcium.body


def test_the_calcium_note_without_symptoms_stays_plain():
    assert "clinician" not in coaching([], TODAY)[-1].body


def test_no_note_mentions_cravings_or_eating_more():
    # The chocolate-craving script is largely an American cultural artefact, and
    # "eat more in the luteal phase" manufactures the pattern that seems to prove it.
    notes = coaching([day(-1, "medium", "cramps", "bloating"), day(0, "heavy")], TODAY)
    for note in notes:
        text = f"{note.title} {note.body}".lower()
        assert "chocolate" not in text
        assert "craving" not in text
        assert "eat more" not in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cycle_rules.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'app.cycle'`

- [ ] **Step 3: Write the rules**

Create `app/cycle/__init__.py` (empty) and `app/cycle/rules.py`:

```python
"""What cycle data means, pure.

Three jobs: find the bleeds in a run of logged days, decide whether anything the
user reported calls for a clinician, and choose which coaching applies. None of
it produces a number the targets use. The iron target already averages menstrual
loss and the calorie target does not move with cycle phase (spec, section 8), so
this module has no path to either -- by construction, not by care.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

FLOWS = ("light", "medium", "heavy")

# The symptoms the coaching responds to. No cravings: the perimenstrual chocolate
# script is largely an American cultural artefact, and has no place here.
SYMPTOMS = ("cramps", "bloating", "breast_tenderness", "low_mood")
PMS_SYMPTOMS = frozenset({"bloating", "breast_tenderness", "low_mood"})
SYMPTOM_WORDS = {
    "cramps": "cramps",
    "bloating": "bloating",
    "breast_tenderness": "breast tenderness",
    "low_mood": "low mood",
}

# Bleeding on more than seven consecutive days is one of the validated
# heavy-bleeding signals, and the one the logs can show without asking.
LONG_BLEED_DAYS = 7
# How far back the logs are read, for display and for the signal above.
HISTORY_DAYS = 90
# "Around menstruation", for the vitamin C pairing.
RECENT_BLEED_DAYS = 7
# How far back logged PMS symptoms are named in the calcium note.
PMS_LOOKBACK_DAYS = 30
# Ginger and fenugreek were trialled on days 1-3 of menses only.
EARLY_BLEED_DAYS = 3

SCREENING_REASONS = (
    ("soaks_within_two_hours", "You reported soaking through a pad or tampon in two hours or less."),
    ("longer_than_seven_days", "You reported periods that last more than seven days."),
    ("large_clots", "You reported passing clots larger than a ₹10 coin."),
    ("flooding", "You reported flooding through to clothes or bedding."),
)


@dataclass(frozen=True)
class Day:
    date: datetime.date
    flow: str | None
    symptoms: frozenset[str]


@dataclass(frozen=True)
class Screening:
    answered_on: datetime.date
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool


@dataclass(frozen=True)
class Bleed:
    start: datetime.date
    end: datetime.date

    @property
    def length(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    evidence: str  # strong | moderate | low | traditional


COFFEE_TIMING = Note(
    id="coffee-timing",
    title="Keep coffee and tea an hour away from meals",
    body=(
        "In young Indian women, one cup of tea with a rice meal cut iron absorption by about "
        "49%, and two cups by about 67%. A one-hour gap roughly halves that."
    ),
    evidence="strong",
)

VITAMIN_C = Note(
    id="vitamin-c",
    title="Pair iron-rich meals with lemon, tomato, tamarind, amla or guava",
    body=(
        "Around your period, have something rich in vitamin C with the meal that carries your "
        "iron: it markedly improves how much of the iron in a rice-and-dal meal is absorbed. "
        "The mechanism is well established. This changes what to eat alongside, not how much "
        "iron you need."
    ),
    evidence="moderate",
)

GINGER = Note(
    id="ginger",
    title="Dry ginger (sukku), 750–2,000 mg a day on days 1–3",
    body=(
        "About half to one level teaspoon of dry ginger powder a day (a level teaspoon is "
        "roughly 1.8 g), split across meals, on the first three days of your period only. It "
        "compared well with mefenamic acid and ibuprofen in head-to-head trials for period "
        "pain, but painkillers such as ibuprofen still work better than any food. This is not "
        "a substitute for treatment."
    ),
    evidence="moderate",
)

FENUGREEK = Note(
    id="fenugreek",
    title="Fenugreek (methi) seed powder, 2.7–4 g a day on days 1–3",
    body=(
        "About one level teaspoon of powder a day, on the first three days, over two cycles. "
        "One small trial supports it, and it was of low quality: something to try, not a "
        "treatment."
    ),
    evidence="low",
)

CALCIUM_BODY = (
    "The only nutrient both ACOG and RCOG endorse for PMS. Typical intake among Indian women "
    "is around 270–500 mg a day. The trial took three cycles to show benefit, so give it time."
)

# Said whenever PMS symptoms were logged: severe PMS, and the low mood of PMDD
# especially, has effective clinical treatment, and a nutrient is not it.
PMS_TREATMENT = (
    "If these symptoms are severe or get in the way of daily life, low mood especially, see "
    "a clinician: there are effective treatments, and calcium is not a substitute for them."
)


def bleeds(days: Sequence[Day]) -> list[Bleed]:
    """Runs of consecutive logged bleeding days, oldest first."""
    runs: list[Bleed] = []
    for date in sorted(d.date for d in days if d.flow is not None):
        if runs and date - runs[-1].end == datetime.timedelta(days=1):
            runs[-1] = Bleed(runs[-1].start, date)
        else:
            runs.append(Bleed(date, date))
    return runs


def last_period_start(days: Sequence[Day]) -> datetime.date | None:
    runs = bleeds(days)
    return runs[-1].start if runs else None


def bleed_day(days: Sequence[Day], today: datetime.date) -> int | None:
    """Which day of a bleed today is, counting from logged bleeding: 1 on its first day.

    A bleed is current if it was logged today or yesterday -- today's log may simply
    not be in yet. Anything older is not current, and nothing is predicted.
    """
    runs = [run for run in bleeds(days) if run.start <= today]
    if not runs or (today - runs[-1].end).days > 1:
        return None
    return (today - runs[-1].start).days + 1


def referral_reason(
    days: Sequence[Day], screening: Screening | None, today: datetime.date
) -> str | None:
    """Why a clinician should see this, in whole sentences -- or None.

    Never a nutrient change. Flow logged as "heavy" is not on its own a trigger:
    it is a self-rating, not one of the validated questions.
    """
    reasons = []
    if screening is not None:
        reasons += [text for field, text in SCREENING_REASONS if getattr(screening, field)]

    recent = [run for run in bleeds(days) if 0 <= (today - run.end).days <= HISTORY_DAYS]
    long_runs = [run for run in recent if run.length > LONG_BLEED_DAYS]
    if long_runs:
        reasons.append(f"You logged bleeding on {long_runs[-1].length} days in a row.")

    return " ".join(reasons) if reasons else None


def coaching(days: Sequence[Day], today: datetime.date) -> list[Note]:
    """The notes that apply today, most broadly useful first."""
    notes = [COFFEE_TIMING]

    runs = [run for run in bleeds(days) if run.start <= today]
    if runs and (today - runs[-1].end).days < RECENT_BLEED_DAYS:
        notes.append(VITAMIN_C)

    current = bleed_day(days, today)
    if current is not None and current <= EARLY_BLEED_DAYS:
        started = today - datetime.timedelta(days=current - 1)
        if any("cramps" in d.symptoms for d in days if started <= d.date <= today):
            notes += [GINGER, FENUGREEK]

    pms = {
        symptom
        for d in days
        if 0 <= (today - d.date).days <= PMS_LOOKBACK_DAYS
        for symptom in d.symptoms
        if symptom in PMS_SYMPTOMS
    }
    notes.append(_calcium(pms))
    return notes


def _calcium(pms: set[str]) -> Note:
    body = CALCIUM_BODY
    if pms:
        named = _join([SYMPTOM_WORDS[s] for s in SYMPTOMS if s in pms])
        body = f"You logged {named} recently. {CALCIUM_BODY} {PMS_TREATMENT}"
    return Note(
        id="calcium", title="Calcium at 1,000–1,200 mg a day", body=body, evidence="moderate"
    )


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} and {words[-1]}"
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_cycle_rules.py -q && uv run ruff check app/cycle tests/test_cycle_rules.py`
Expected: all PASS, ruff clean. Wrap the long `SCREENING_REASONS` lines if they exceed 100 columns.

- [ ] **Step 5: Commit**

```bash
git add app/cycle/__init__.py app/cycle/rules.py tests/test_cycle_rules.py
git commit -m "feat(backend): add the cycle rules -- bleeds, referral, coaching

Pure functions over logged days. A bleed is a run of consecutive logged
bleeding days and \"day 1-3\" counts from it; nothing predicts a phase, since
only 13% of cycles are 28 days. The heavy-bleeding referral comes from the
validated screening questions or more than seven logged days in a row, never
from a self-rated heavy flow. Coaching is symptom-driven: ginger and
fenugreek only for cramps early in a bleed, each note with its evidence grade,
the plain statement that painkillers outperform any food, and a pointer to a
clinician whenever PMS symptoms were logged.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: The cycle service and API

**Files:**
- Create: `app/cycle/service.py`, `app/cycle/router.py`
- Modify: `app/main.py`
- Test: `tests/test_cycle_api.py` (create)

**Interfaces:**
- Consumes: `app.cycle.rules` (Task 7), the cycle models (Task 3), `profiles.get_profile`
- Produces the HTTP contract that Task 10 writes into `frontend/src/cycle/types.ts`:

| Method and path | Body | Answer |
|---|---|---|
| `GET /cycle?date=` | — | 200 `CycleOut`. `date` is optional, defaults to the user's today, and is the day coaching is read against. 404 with no profile |
| `PATCH /cycle` | `{enabled}` | 200 `CycleOut`; 409 when the profile is not eligible |
| `DELETE /cycle` | — | 204. Every cycle row the user has is erased |
| `PUT /cycle/days/{date}` | `{flow: light\|medium\|heavy\|null, symptoms: [...]}` | 200 `CycleOut`. It replaces the day, and an empty day clears it. 422 for a future date or an unknown value; 409 while tracking is off |
| `DELETE /cycle/days/{date}` | — | 204; 404 when nothing is logged on that date |
| `POST /cycle/screening` | `{soaks_within_two_hours, longer_than_seven_days, large_clots, flooding, date?}` | 200 `CycleOut`; 409 while tracking is off |

```
CycleOut {
  eligible
  ineligible_reason: "not-female" | "postmenopausal" | null
  enabled
  has_history                          # any cycle row exists, even while hidden
  last_period_start
  days: [{date, flow, symptoms}]      # newest first
  screening: {answered_on, ...four} | null
  coaching: [{id, title, body, evidence}]
  referral: {reason} | null
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cycle_api.py`:

```python
"""The cycle API -- and the two rules a well-meaning change would get wrong.

THE TWO COUNTER-INTUITIVE RULES, LOCKED IN.

1. Logging a period must leave the iron target exactly where it was. ICMR's
   29 mg/day for women ALREADY averages menstrual loss across the cycle, so
   raising it on bleed days counts that loss twice. The giveaway is ICMR's
   pregnancy RDA, 27 mg: lower than the non-pregnant figure, which only makes
   sense if menstruation is baked into the 29. Offsetting the loss in real time
   would take ~37 mg of extra dietary iron a day anyway, and hepcidin already
   raises absorption during menses.

2. Cycle phase must never move the calorie target. The luteal rise in resting
   expenditure is ~32 kcal/day once anovulatory cycles are counted -- inside the
   noise of intake -- and an app that expects more eating in the luteal phase
   manufactures the logging pattern that would seem to prove it right.

Both are exactly what a future change would "helpfully" fix. These tests stop it.
"""

import ast
import datetime
import pathlib
import zoneinfo

from app.models.cycle import CycleLog
from app.models.user import User
from tests.test_tracking_api import PROFILE, nutrient

TODAY = datetime.date(2026, 8, 17)
REAL_TODAY = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()

WOMAN = {**PROFILE, "sex": "female", "weight_kg": 55.0, "menstrual_status": "menstruating"}
ALL_NO = {
    "soaks_within_two_hours": False,
    "longer_than_seven_days": False,
    "large_clots": False,
    "flooding": False,
}

CYCLE_TABLE_MODULES = ("app.cycle", "app.models.cycle")
CYCLE_MODELS = {"CycleLog", "CycleScreening", "CycleSettings", "CycleSymptom"}


def on(offset: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=offset)


def cycle(api, date: datetime.date = TODAY) -> dict:
    response = api.get(f"/cycle?date={date}")
    assert response.status_code == 200, response.text
    return response.json()


def tracking(api, profile: dict = WOMAN):
    assert api.put("/profile", json=profile).status_code == 200
    assert api.patch("/cycle", json={"enabled": True}).status_code == 200
    return api


def log(api, date: datetime.date, flow: str | None = None, *symptoms: str):
    response = api.put(f"/cycle/days/{date}", json={"flow": flow, "symptoms": list(symptoms)})
    assert response.status_code == 200, response.text


def note_ids(state: dict) -> list[str]:
    return [note["id"] for note in state["coaching"]]


# --- access ---------------------------------------------------------------------------------


def test_cycle_needs_a_session(api_client):
    assert api_client.get("/cycle").status_code == 401


def test_cycle_needs_a_profile(signed_in):
    assert signed_in.get("/cycle").status_code == 404


def test_a_man_is_not_offered_cycle_tracking(signed_in):
    signed_in.put("/profile", json=PROFILE)
    state = cycle(signed_in)

    assert state["eligible"] is False
    assert state["ineligible_reason"] == "not-female"
    assert signed_in.patch("/cycle", json={"enabled": True}).status_code == 409


def test_nor_is_a_woman_after_menopause(signed_in):
    signed_in.put("/profile", json={**WOMAN, "menstrual_status": "postmenopausal"})

    assert cycle(signed_in)["ineligible_reason"] == "postmenopausal"
    assert signed_in.patch("/cycle", json={"enabled": True}).status_code == 409


def test_another_users_cycle_data_is_invisible(signed_in, db):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(CycleLog(user_id=other.id, logged_on=on(-1), flow="heavy"))
    db.flush()

    tracking(signed_in)
    assert cycle(signed_in)["days"] == []


# --- the switch -----------------------------------------------------------------------------


def test_tracking_is_off_until_turned_on(signed_in):
    signed_in.put("/profile", json=WOMAN)
    state = cycle(signed_in)

    assert state["eligible"] is True
    assert state["enabled"] is False
    assert state["coaching"] == []


def test_turning_it_on_brings_the_coaching(signed_in):
    state = cycle(tracking(signed_in))

    assert state["enabled"] is True
    assert note_ids(state) == ["coffee-timing", "calcium"]
    assert all(note["evidence"] for note in state["coaching"])


def test_nothing_is_logged_while_tracking_is_off(signed_in):
    signed_in.put("/profile", json=WOMAN)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": "medium", "symptoms": []})
    assert response.status_code == 409


def test_turning_it_off_hides_the_log_but_keeps_it(signed_in):
    log(tracking(signed_in), on(-1), "medium")

    signed_in.patch("/cycle", json={"enabled": False})
    assert cycle(signed_in)["days"] == []

    signed_in.patch("/cycle", json={"enabled": True})
    assert len(cycle(signed_in)["days"]) == 1


def test_history_left_behind_by_a_profile_change_can_still_be_erased(signed_in):
    log(tracking(signed_in), on(-1), "medium")
    signed_in.put("/profile", json={**WOMAN, "menstrual_status": "postmenopausal"})

    state = cycle(signed_in)
    assert state["eligible"] is False
    assert state["days"] == []
    assert state["has_history"] is True

    assert signed_in.delete("/cycle").status_code == 204
    assert cycle(signed_in)["has_history"] is False


def test_erasing_removes_everything(signed_in):
    log(tracking(signed_in), on(-1), "medium", "cramps")
    signed_in.post("/cycle/screening", json={**ALL_NO, "date": str(TODAY)})

    assert signed_in.delete("/cycle").status_code == 204
    assert cycle(signed_in)["enabled"] is False

    signed_in.patch("/cycle", json={"enabled": True})
    state = cycle(signed_in)
    assert state["days"] == []
    assert state["screening"] is None


# --- logging days ---------------------------------------------------------------------------


def test_a_day_is_logged_and_read_back(signed_in):
    log(tracking(signed_in), on(-1), "medium", "cramps", "bloating")
    state = cycle(signed_in)

    assert state["days"] == [
        {"date": str(on(-1)), "flow": "medium", "symptoms": ["bloating", "cramps"]}
    ]
    assert state["last_period_start"] == str(on(-1))


def test_days_come_newest_first(signed_in):
    tracking(signed_in)
    log(signed_in, on(-2), "light")
    log(signed_in, on(-1), "medium")
    assert [d["date"] for d in cycle(signed_in)["days"]] == [str(on(-1)), str(on(-2))]


def test_logging_a_day_again_replaces_it(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium", "cramps")
    log(signed_in, on(-1), "heavy")

    assert cycle(signed_in)["days"] == [{"date": str(on(-1)), "flow": "heavy", "symptoms": []}]


def test_a_symptom_can_be_logged_without_bleeding(signed_in):
    log(tracking(signed_in), on(-3), None, "bloating")
    state = cycle(signed_in)

    assert state["days"][0]["flow"] is None
    assert state["last_period_start"] is None


def test_an_empty_day_clears_it(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium")
    log(signed_in, on(-1))
    assert cycle(signed_in)["days"] == []


def test_a_day_can_be_removed(signed_in):
    log(tracking(signed_in), on(-1), "medium")

    assert signed_in.delete(f"/cycle/days/{on(-1)}").status_code == 204
    assert signed_in.delete(f"/cycle/days/{on(-1)}").status_code == 404


def test_a_future_day_is_refused(signed_in):
    tracking(signed_in)
    tomorrow = REAL_TODAY + datetime.timedelta(days=1)
    response = signed_in.put(f"/cycle/days/{tomorrow}", json={"flow": "light", "symptoms": []})
    assert response.status_code == 422


def test_cravings_are_not_a_symptom_here(signed_in):
    tracking(signed_in)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": None, "symptoms": ["cravings"]})
    assert response.status_code == 422


def test_an_unknown_flow_is_refused(signed_in):
    tracking(signed_in)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": "spotting", "symptoms": []})
    assert response.status_code == 422


# --- coaching and referral ------------------------------------------------------------------


def test_ginger_follows_cramps_early_in_a_bleed_only(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium", "cramps")
    log(signed_in, on(0), "heavy")

    assert "ginger" in note_ids(cycle(signed_in, TODAY))
    assert "ginger" not in note_ids(cycle(signed_in, on(3)))


def test_a_yes_on_the_screening_refers_to_a_clinician(signed_in):
    tracking(signed_in)
    response = signed_in.post(
        "/cycle/screening",
        json={**ALL_NO, "soaks_within_two_hours": True, "date": str(TODAY)},
    )
    assert response.status_code == 200

    state = cycle(signed_in)
    assert "two hours" in state["referral"]["reason"]
    assert state["screening"]["soaks_within_two_hours"] is True


def test_answering_no_again_withdraws_the_referral(signed_in):
    tracking(signed_in)
    signed_in.post("/cycle/screening", json={**ALL_NO, "flooding": True, "date": str(on(-7))})
    signed_in.post("/cycle/screening", json={**ALL_NO, "date": str(TODAY)})
    assert cycle(signed_in)["referral"] is None


def test_eight_days_in_a_row_refers_to_a_clinician(signed_in):
    tracking(signed_in)
    for offset in range(-8, 0):
        log(signed_in, on(offset), "medium")
    assert "8 days in a row" in cycle(signed_in)["referral"]["reason"]


def test_heavy_flow_alone_does_not_refer(signed_in):
    tracking(signed_in)
    for offset in range(-3, 0):
        log(signed_in, on(offset), "heavy")
    assert cycle(signed_in)["referral"] is None


def test_screening_needs_tracking_on(signed_in):
    signed_in.put("/profile", json=WOMAN)
    assert signed_in.post("/cycle/screening", json=ALL_NO).status_code == 409


# --- THE LOCKED RULES -----------------------------------------------------------------------


def targets(api, date: datetime.date) -> dict:
    response = api.get(f"/targets/today?date={date}")
    assert response.status_code == 200, response.text
    return response.json()


def the_heaviest_cycle_there_is(api):
    """Heavy bleeding with cramps for three days, and a yes to every screening question."""
    for offset in range(-2, 1):
        log(api, on(offset), "heavy", "cramps", "bloating")
    yes = dict.fromkeys(ALL_NO, True)
    assert api.post("/cycle/screening", json={**yes, "date": str(TODAY)}).status_code == 200


def test_logging_a_period_does_not_raise_the_iron_target(signed_in, iron_reference):
    tracking(signed_in)
    before = nutrient(targets(signed_in, TODAY), "iron")

    the_heaviest_cycle_there_is(signed_in)

    after = nutrient(targets(signed_in, TODAY), "iron")
    assert after["rda"] == before["rda"] == 29
    assert after["target_effective"] == before["target_effective"]
    # The referral is the answer to heavy bleeding -- not a raised iron goal.
    assert cycle(signed_in)["referral"] is not None


def test_cycle_phase_never_moves_the_calorie_target(signed_in, iron_reference):
    tracking(signed_in)
    dates = [on(-2), TODAY, on(7), on(14), on(21)]  # bleed days, follicular, luteal
    before = {d: nutrient(targets(signed_in, d), "energy") for d in dates}

    the_heaviest_cycle_there_is(signed_in)

    for d in dates:
        after = nutrient(targets(signed_in, d), "energy")
        assert after["rda"] == before[d]["rda"]
        assert after["target_effective"] == before[d]["target_effective"]


def test_nothing_in_the_targets_path_imports_cycle_code():
    """The rule is structural: the modules that compute targets never see cycle data."""
    app = pathlib.Path(__file__).resolve().parent.parent / "app"
    paths = [
        path
        for package in ("nutrition_core", "targets", "planner", "weight")
        for path in (app / package).glob("*.py")
    ]
    assert paths

    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules, names = [alias.name for alias in node.names], []
            elif isinstance(node, ast.ImportFrom):
                modules, names = [node.module or ""], [alias.name for alias in node.names]
            else:
                continue
            assert not any(m.startswith(CYCLE_TABLE_MODULES) for m in modules), path
            assert not CYCLE_MODELS & set(names), path
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_cycle_api.py -q`
Expected: FAIL, with `/cycle` answering 404 `Not Found`. The import test passes already, and should.

- [ ] **Step 3: Write the service**

Create `app/cycle/service.py`:

```python
"""Cycle tracking: the switch, logged days, and screening answers.

Nothing in the targets path imports this module, and it imports nothing from
the targets path. The separation is the rule, not an accident of layout: the
iron target already averages menstrual loss and calories do not move with cycle
phase, so cycle data has nothing to tell the targets. `tests/test_cycle_api.py`
checks the imports.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cycle import rules
from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.profile import Profile
from app.models.user import User
from app.profiles import service as profiles

OWNED = (CycleLog, CycleSymptom, CycleScreening, CycleSettings)


class NoProfile(LookupError):
    """No profile, so no way to know whether tracking applies."""


class NotEligible(ValueError):
    """Tracking is for a woman's profile that is not postmenopausal."""


class NotEnabled(ValueError):
    """Tracking is off, and nothing is logged until it is turned on."""


@dataclass(frozen=True)
class CycleView:
    eligible: bool
    ineligible_reason: str | None  # not-female | postmenopausal
    enabled: bool
    # Rows exist even when hidden -- tracking off, or the profile no longer
    # eligible -- so the screen can still offer to erase them.
    has_history: bool
    last_period_start: datetime.date | None
    days: list[rules.Day]  # newest first
    screening: rules.Screening | None
    coaching: list[rules.Note]
    referral: str | None


def ineligible_reason(profile: Profile) -> str | None:
    if profile.sex != "female":
        return "not-female"
    if profile.menstrual_status == "postmenopausal":
        return "postmenopausal"
    return None


def set_enabled(db: Session, user: User, enabled: bool) -> None:
    profile = _profile(db, user)
    if enabled and ineligible_reason(profile) is not None:
        raise NotEligible
    settings = _settings(db, user)
    if settings is None:
        settings = CycleSettings(user_id=user.id)
        db.add(settings)
    settings.enabled = enabled
    db.flush()


def save_day(
    db: Session, user: User, on_date: datetime.date, flow: str | None, symptoms: list[str]
) -> None:
    """Replace what is logged for one day. No flow and no symptoms clears it."""
    _require_tracking(db, user)
    clear_day(db, user, on_date)
    if flow is not None:
        db.add(CycleLog(user_id=user.id, logged_on=on_date, flow=flow))
    db.add_all(
        [
            CycleSymptom(user_id=user.id, logged_on=on_date, symptom=symptom)
            for symptom in sorted(set(symptoms))
        ]
    )
    db.flush()


def clear_day(db: Session, user: User, on_date: datetime.date) -> bool:
    """Remove a day's log. Allowed whether or not tracking is on: it is the user's data."""
    removed = 0
    for model in (CycleLog, CycleSymptom):
        result = db.execute(
            delete(model).where(model.user_id == user.id, model.logged_on == on_date)
        )
        removed += result.rowcount
    db.flush()
    return removed > 0


def save_screening(
    db: Session,
    user: User,
    on_date: datetime.date,
    *,
    soaks_within_two_hours: bool,
    longer_than_seven_days: bool,
    large_clots: bool,
    flooding: bool,
) -> None:
    _require_tracking(db, user)
    row = db.scalars(
        select(CycleScreening).where(
            CycleScreening.user_id == user.id, CycleScreening.answered_on == on_date
        )
    ).one_or_none()
    if row is None:
        row = CycleScreening(user_id=user.id, answered_on=on_date)
        db.add(row)
    row.soaks_within_two_hours = soaks_within_two_hours
    row.longer_than_seven_days = longer_than_seven_days
    row.large_clots = large_clots
    row.flooding = flooding
    db.flush()


def erase(db: Session, user: User) -> None:
    """Every cycle row the user has, the switch included: back to never having used it."""
    for model in OWNED:
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()


def view(db: Session, user: User, today: datetime.date) -> CycleView:
    profile = _profile(db, user)
    reason = ineligible_reason(profile)
    settings = _settings(db, user)
    enabled = reason is None and settings is not None and settings.enabled
    has_history = any(
        db.scalar(select(model.id).where(model.user_id == user.id).limit(1)) is not None
        for model in (CycleLog, CycleSymptom, CycleScreening)
    )
    if not enabled:
        # Off means off: the logs are kept, but nothing about them is shown or read.
        return CycleView(
            eligible=reason is None,
            ineligible_reason=reason,
            enabled=False,
            has_history=has_history,
            last_period_start=None,
            days=[],
            screening=None,
            coaching=[],
            referral=None,
        )

    days = _days(db, user, since=today - datetime.timedelta(days=rules.HISTORY_DAYS), until=today)
    screening = _latest_screening(db, user)
    return CycleView(
        eligible=True,
        ineligible_reason=None,
        enabled=True,
        has_history=has_history,
        last_period_start=rules.last_period_start(days),
        days=days,
        screening=screening,
        coaching=rules.coaching(days, today),
        referral=rules.referral_reason(days, screening, today),
    )


def _profile(db: Session, user: User) -> Profile:
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile
    return profile


def _settings(db: Session, user: User) -> CycleSettings | None:
    return db.scalars(select(CycleSettings).where(CycleSettings.user_id == user.id)).one_or_none()


def _require_tracking(db: Session, user: User) -> None:
    if ineligible_reason(_profile(db, user)) is not None:
        raise NotEligible
    settings = _settings(db, user)
    if settings is None or not settings.enabled:
        raise NotEnabled


def _days(
    db: Session, user: User, since: datetime.date, until: datetime.date
) -> list[rules.Day]:
    flows = {
        row.logged_on: row.flow
        for row in db.scalars(
            select(CycleLog).where(
                CycleLog.user_id == user.id,
                CycleLog.logged_on >= since,
                CycleLog.logged_on <= until,
            )
        )
    }
    symptoms: dict[datetime.date, set[str]] = defaultdict(set)
    for row in db.scalars(
        select(CycleSymptom).where(
            CycleSymptom.user_id == user.id,
            CycleSymptom.logged_on >= since,
            CycleSymptom.logged_on <= until,
        )
    ):
        symptoms[row.logged_on].add(row.symptom)

    return [
        rules.Day(date=date, flow=flows.get(date), symptoms=frozenset(symptoms.get(date, ())))
        for date in sorted(set(flows) | set(symptoms), reverse=True)
    ]


def _latest_screening(db: Session, user: User) -> rules.Screening | None:
    row = db.scalars(
        select(CycleScreening)
        .where(CycleScreening.user_id == user.id)
        .order_by(CycleScreening.answered_on.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return rules.Screening(
        answered_on=row.answered_on,
        soaks_within_two_hours=row.soaks_within_two_hours,
        longer_than_seven_days=row.longer_than_seven_days,
        large_clots=row.large_clots,
        flooding=row.flooding,
    )
```

- [ ] **Step 4: Write the router**

Create `app/cycle/router.py`:

```python
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.cycle import rules, service
from app.db import get_db
from app.local_time import local_today
from app.models.user import User

router = APIRouter(prefix="/cycle", tags=["cycle"])

NOT_ELIGIBLE = "Cycle tracking is for a woman's profile that is not postmenopausal"


class CycleDayOut(BaseModel):
    date: datetime.date
    flow: str | None
    symptoms: list[str]


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    evidence: str


class ScreeningOut(BaseModel):
    answered_on: datetime.date
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool


class ReferralOut(BaseModel):
    reason: str


class CycleOut(BaseModel):
    eligible: bool
    ineligible_reason: str | None
    enabled: bool
    has_history: bool
    last_period_start: datetime.date | None
    days: list[CycleDayOut]
    screening: ScreeningOut | None
    coaching: list[NoteOut]
    referral: ReferralOut | None


class EnabledIn(BaseModel):
    enabled: bool


class DayIn(BaseModel):
    flow: str | None = Field(default=None, pattern="^(light|medium|heavy)$")
    symptoms: list[str] = []


class ScreeningIn(BaseModel):
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool
    date: datetime.date | None = None


def _out(view: service.CycleView) -> CycleOut:
    return CycleOut(
        eligible=view.eligible,
        ineligible_reason=view.ineligible_reason,
        enabled=view.enabled,
        has_history=view.has_history,
        last_period_start=view.last_period_start,
        days=[
            CycleDayOut(date=day.date, flow=day.flow, symptoms=sorted(day.symptoms))
            for day in view.days
        ],
        screening=ScreeningOut(**vars(view.screening)) if view.screening is not None else None,
        coaching=[NoteOut(**vars(note)) for note in view.coaching],
        referral=ReferralOut(reason=view.referral) if view.referral is not None else None,
    )


def _read(db: Session, user: User, on_date: datetime.date) -> CycleOut:
    try:
        return _out(service.view(db, user, on_date))
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


def _not_in_the_future(on_date: datetime.date, user: User) -> None:
    if on_date > local_today(user):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A cycle log cannot be dated in the future"
        )


def _refusal(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NoProfile):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first")
    if isinstance(exc, service.NotEligible):
        return HTTPException(status.HTTP_409_CONFLICT, NOT_ELIGIBLE)
    return HTTPException(status.HTTP_409_CONFLICT, "Turn cycle tracking on first")


@router.get("", response_model=CycleOut)
def read_cycle(
    date: datetime.date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    """`date` is the client's today: coaching such as "days 1-3" is read against it."""
    return _read(db, user, date or local_today(user))


@router.patch("", response_model=CycleOut)
def set_enabled(
    payload: EnabledIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    try:
        service.set_enabled(db, user, payload.enabled)
    except (service.NoProfile, service.NotEligible) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def erase(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    service.erase(db, user)
    db.commit()


@router.put("/days/{on_date}", response_model=CycleOut)
def save_day(
    on_date: datetime.date,
    payload: DayIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    _not_in_the_future(on_date, user)
    unknown = sorted(set(payload.symptoms) - set(rules.SYMPTOMS))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown symptoms: {unknown}"
        )
    try:
        service.save_day(db, user, on_date, payload.flow, payload.symptoms)
    except (service.NoProfile, service.NotEligible, service.NotEnabled) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))


@router.delete("/days/{on_date}", status_code=status.HTTP_204_NO_CONTENT)
def clear_day(
    on_date: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not service.clear_day(db, user, on_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing logged on that date")
    db.commit()


@router.post("/screening", response_model=CycleOut)
def answer_screening(
    payload: ScreeningIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    on_date = payload.date or local_today(user)
    _not_in_the_future(on_date, user)
    try:
        service.save_screening(
            db,
            user,
            on_date,
            soaks_within_two_hours=payload.soaks_within_two_hours,
            longer_than_seven_days=payload.longer_than_seven_days,
            large_clots=payload.large_clots,
            flooding=payload.flooding,
        )
    except (service.NoProfile, service.NotEligible, service.NotEnabled) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))
```

In `app/main.py`, add `from app.cycle.router import router as cycle_router` in import order (after the `app.config` import) and `app.include_router(cycle_router)` after the weight router.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_cycle_api.py tests/test_cycle_rules.py tests/test_menstrual_status.py -q && uv run ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/cycle/service.py app/cycle/router.py app/main.py tests/test_cycle_api.py
git commit -m "feat(backend): add the cycle API, and lock in the two rules it must not break

GET/PATCH/DELETE /cycle, PUT/DELETE /cycle/days/{date} and POST
/cycle/screening. Tracking is off until turned on, offered only to a woman's
profile that is not postmenopausal, and nothing is logged while it is off;
turning it off hides the log without deleting it, and DELETE /cycle erases it.

Two regression tests say out loud what a future change must not do: the
heaviest cycle there is -- three heavy days, cramps, a yes to every screening
question -- leaves the iron target at 29 mg and the calorie target where it
was on every day of the cycle. A third checks that nothing in the targets
path imports cycle code at all.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
## Task 9: Frontend — the Weight screen on the real endpoint

**Files:**
- Modify:
  - `src/weight/types.ts`
  - `src/weight/WeightScreen.tsx`
  - `src/lib/format.ts`, `src/lib/format.test.ts`: `formatDay`
  - `src/mocks/fixtures/more.ts`: `WEIGHT_FIXTURE`
  - `src/mocks/handlers/index.ts`: delete the two weight handlers
- Create: `src/weight/useWeight.ts`, `src/weight/WeightScreen.test.tsx`

**Interfaces:**
- Consumes: the Task 5 contract
- Produces: `formatDay(iso: string): string`, which renders `'2026-08-03'` as `'3 Aug 2026'` and is also used by Task 10

- [ ] **Step 1: Write the contract as built**

Replace `src/weight/types.ts`:

```ts
import type { Goal } from '../onboarding/types'

/**
 * CONTRACT for `GET /weight`, `POST /weight` and `DELETE /weight/{date}` — plan 7.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec: the
 * smoothed weight is null before the first weigh-in, the observed rate is its own
 * field, an adjustment says since when, and a weigh-in may carry a date.
 */

export interface WeighIn {
  date: string
  weight_kg: number
}

export interface NewWeighIn {
  weight_kg: number
  /** Defaults to the user's today on the server. A missed week can be filled in. */
  date?: string
}

export interface CalorieAdjustment {
  /**
   * Against the formula's figure. Bounded to ±10%, never below BMR, and a loss
   * target never below 1,200 kcal (women) or 1,500 kcal (men) unless maintenance
   * itself is lower.
   */
  delta_kcal: number
  since: string
  reason: string
}

export interface WeightTrend {
  /** Oldest first, the last year. The profile's weight is the newest of these. */
  weigh_ins: WeighIn[]
  /** Mean of the last three weigh-ins, so water weight does not cause thrash. */
  smoothed_kg: number | null
  goal: Goal
  /** What the goal's formula target implies, from its real deficit. */
  expected_kg_per_week: number
  /** Fitted over the last four weeks since the last step; null until three weigh-ins span two weeks. */
  observed_kg_per_week: number | null
  /** Today's energy target — the same figure the Today screen shows. */
  calorie_target_kcal: number
  adjustment: CalorieAdjustment | null
  /** One sentence on where the trend stands, or null. */
  note: string | null
}
```

Replace `WEIGHT_FIXTURE` in `src/mocks/fixtures/more.ts`:

```ts
export const WEIGHT_FIXTURE: WeightTrend = {
  weigh_ins: [
    { date: '2026-07-19', weight_kg: 74.8 },
    { date: '2026-07-26', weight_kg: 74.9 },
    { date: '2026-08-02', weight_kg: 74.4 },
    { date: '2026-08-09', weight_kg: 74.1 },
    { date: '2026-08-16', weight_kg: 74.2 },
  ],
  smoothed_kg: 74.2,
  goal: 'lose',
  expected_kg_per_week: -0.4,
  observed_kg_per_week: -0.1,
  calorie_target_kcal: 2020,
  adjustment: {
    delta_kcal: -90,
    since: '2026-08-16',
    reason:
      'Your weight has fallen about 0.1 kg a week against a goal of losing about 0.4 kg a week, so your calorie target moves down a bounded step. It stays within 10% of what the formula gives and never goes below a safe floor.',
  },
  note: 'Your target last moved on 16 August. The next reading needs three weigh-ins across at least two weeks after that.',
}
```

In `src/mocks/handlers/index.ts`, delete the two `/weight` handlers and `WEIGHT_FIXTURE` from the import. Leave the cycle handlers for Task 10. Then rewrite the comment above the list to say that the weight endpoints are real now: "…the tracking loop — profile, targets and diary — the meal planner and weight exist in FastAPI…".

- [ ] **Step 2: Write the failing tests**

Add to `src/lib/format.test.ts`:

```ts
test('a calendar date reads as a day, month and year', () => {
  expect(formatDay('2026-08-03')).toBe('3 Aug 2026')
})

test('a date is not shifted by the timezone it is read in', () => {
  // `new Date('2026-08-01')` is UTC midnight, which is 31 July west of Greenwich.
  expect(formatDay('2026-08-01')).toBe('1 Aug 2026')
})
```

(Add `formatDay` to that file's import from `./format`.)

Create `src/weight/WeightScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { WEIGHT_FIXTURE } from '../mocks/fixtures/more'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { WeightScreen } from './WeightScreen'
import type { WeightTrend } from './types'

let posted: unknown = null
let deleted: string | null = null

function stubTrend(trend: WeightTrend) {
  server.use(http.get(apiUrl('/weight'), () => HttpResponse.json(trend)))
}

beforeEach(() => {
  posted = null
  deleted = null
  server.use(
    http.get(apiUrl('/weight'), () => HttpResponse.json(WEIGHT_FIXTURE)),
    http.post(apiUrl('/weight'), async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json(WEIGHT_FIXTURE, { status: 201 })
    }),
    http.delete(apiUrl('/weight/:date'), ({ params }) => {
      deleted = params.date as string
      return new HttpResponse(null, { status: 204 })
    }),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WeightScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('shows the trend from the real endpoint, with no demo banner', async () => {
  renderScreen()

  expect(await screen.findByRole('rowheader', { name: '16 Aug 2026' })).toBeInTheDocument()
  expect(screen.getByText('losing about 0.4 kg a week')).toBeInTheDocument()
  expect(screen.getByText('losing about 0.1 kg a week')).toBeInTheDocument()
  expect(screen.getByText('2,020 kcal a day')).toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

test('sends the weigh-in with its date, and clears the field once saved', async () => {
  renderScreen()

  const field = await screen.findByLabelText('Weight in kg')
  expect(screen.getByLabelText('Date')).toHaveValue(todayIso())
  await userEvent.type(field, '74.0')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(posted).toEqual({ weight_kg: 74, date: todayIso() }))
  await waitFor(() => expect(field).toHaveValue(''))
})

// The energy equations are weight-based: a typo would quietly skew every target.
test('will not save an implausible weight', async () => {
  renderScreen()

  await userEvent.type(await screen.findByLabelText('Weight in kg'), '7.4')

  expect(screen.getByRole('alert')).toHaveTextContent(/between 20 and 300/)
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
})

test('keeps what was typed when the save fails', async () => {
  server.use(http.post(apiUrl('/weight'), () => new HttpResponse('boom', { status: 500 })))
  renderScreen()

  const field = await screen.findByLabelText('Weight in kg')
  await userEvent.type(field, '74')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be saved/)
  expect(field).toHaveValue('74')
})

test('explains a calorie target that moved, and since when', async () => {
  renderScreen()

  expect(await screen.findByRole('heading', { name: /calorie target moved/i })).toBeInTheDocument()
  expect(screen.getByText('-90 kcal')).toBeInTheDocument()
  expect(screen.getByText(/since 16 Aug 2026/)).toBeInTheDocument()
  expect(screen.getByText(/moves down a bounded step/)).toBeInTheDocument()
})

test('says nothing about an adjustment when there is none', async () => {
  stubTrend({ ...WEIGHT_FIXTURE, adjustment: null })
  renderScreen()

  await screen.findByRole('rowheader', { name: '16 Aug 2026' })
  expect(screen.queryByRole('heading', { name: /calorie target moved/i })).not.toBeInTheDocument()
})

test('a weigh-in can be removed', async () => {
  renderScreen()

  await userEvent.click(
    await screen.findByRole('button', { name: 'Remove the weigh-in on 16 Aug 2026' }),
  )

  await waitFor(() => expect(deleted).toBe('2026-08-16'))
})

test('draws no trend line from a single weigh-in', async () => {
  stubTrend({
    ...WEIGHT_FIXTURE,
    weigh_ins: [{ date: '2026-08-16', weight_kg: 65 }],
    smoothed_kg: 65,
    observed_kg_per_week: null,
    adjustment: null,
    note: 'Your trend is read from three weigh-ins across at least two weeks. Weighing in once a week is enough.',
  })
  renderScreen()

  expect(await screen.findByText(/appears after your second weigh-in/)).toBeInTheDocument()
  expect(screen.getByText('Not enough weigh-ins yet')).toBeInTheDocument()
  expect(screen.getByText(/read from three weigh-ins/)).toBeInTheDocument()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(http.get(apiUrl('/weight'), () => new HttpResponse('no profile', { status: 404 })))
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npx vitest run src/weight src/lib/format.test.ts`
Expected: FAIL. `formatDay` is not exported, and the screen still renders the demo banner and has no date field.

- [ ] **Step 4: Implement**

Add to `src/lib/format.ts`:

```ts
/**
 * `3 Aug 2026` from an ISO calendar date.
 *
 * Built from its parts rather than parsed, because `new Date('2026-08-01')` is
 * UTC midnight — which is still 31 July anywhere west of Greenwich.
 */
export function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(year, month - 1, day))
}
```

Create `src/weight/useWeight.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { NewWeighIn, WeightTrend } from './types'

export function useWeight() {
  return useQuery({
    queryKey: ['weight'],
    queryFn: () => api.get<WeightTrend>('/weight'),
    retry: false,
  })
}

/*
 * A weigh-in reaches further than this screen. It is the profile's weight, so
 * the profile summary and the baseline move, and it can recalibrate today's
 * targets. It never rewrites a stored plan, so the plan is left alone.
 */
function afterWeighIn(queryClient: QueryClient) {
  for (const queryKey of [['weight'], ['targets'], ['profile']]) {
    queryClient.invalidateQueries({ queryKey })
  }
}

export function useAddWeighIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (weighIn: NewWeighIn) => api.post<WeightTrend>('/weight', weighIn),
    onSuccess: () => afterWeighIn(queryClient),
  })
}

export function useRemoveWeighIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (date: string) => api.del(`/weight/${date}`),
    onSuccess: () => afterWeighIn(queryClient),
  })
}
```

Replace `src/weight/WeightScreen.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError } from '../lib/api'
import { formatAmount, formatDay } from '../lib/format'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Field, NumberInput, TextInput } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import { useAddWeighIn, useRemoveWeighIn, useWeight } from './useWeight'
import type { WeightTrend } from './types'

// The profile's bounds. The energy equations are weight-based, so a typo here
// would quietly skew every target.
const MIN_KG = 20
const MAX_KG = 300

/** "losing about 0.3 kg a week", for a goal or an observed trend. */
function rateWords(kgPerWeek: number): string {
  if (Math.abs(kgPerWeek) < 0.05) return 'holding steady'
  const direction = kgPerWeek < 0 ? 'losing' : 'gaining'
  return `${direction} about ${Math.abs(kgPerWeek).toFixed(1)} kg a week`
}

function WeighInForm() {
  const addWeighIn = useAddWeighIn()
  const [entry, setEntry] = useState('')
  const [date, setDate] = useState(todayIso)

  const parsed = Number.parseFloat(entry)
  const valid = Number.isFinite(parsed) && parsed > MIN_KG && parsed <= MAX_KG
  const invalid = entry.trim() !== '' && !valid

  return (
    <Card>
      <CardTitle>Add this week’s weigh-in</CardTitle>
      <div className="mt-2 grid gap-x-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field
          label="Weight in kg"
          error={invalid ? `Please give a weight in kg between ${MIN_KG} and ${MAX_KG}.` : undefined}
        >
          {(fieldProps) => (
            <NumberInput
              {...fieldProps}
              value={entry}
              onChange={(event) => setEntry(event.target.value)}
              placeholder="74.2"
            />
          )}
        </Field>
        <Field label="Date">
          {(fieldProps) => (
            <TextInput
              {...fieldProps}
              type="date"
              value={date}
              max={todayIso()}
              onChange={(event) => setDate(event.target.value)}
            />
          )}
        </Field>
        <Button
          variant="primary"
          className="mb-4"
          disabled={!valid || date === '' || addWeighIn.isPending}
          onClick={() =>
            // Cleared only once saved, so a failed save does not lose what was typed.
            addWeighIn.mutate({ weight_kg: parsed, date }, { onSuccess: () => setEntry('') })
          }
        >
          Save
        </Button>
      </div>
      {addWeighIn.isError && (
        <p role="alert" className="mb-2 text-sm text-above-limit">
          That weigh-in could not be saved. Please try again.
        </p>
      )}
      <p className="text-xs text-text-muted">
        Weekly is enough. The trend is read across several weigh-ins, so a day of water weight
        doesn’t trigger a calorie recalibration. A missed week can be filled in by changing
        the date.
      </p>
    </Card>
  )
}

function Summary({ data }: { data: WeightTrend }) {
  return (
    <Card>
      <CardTitle>Where you are</CardTitle>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-text-muted">Smoothed weight</dt>
          <dd className="font-medium">
            {data.smoothed_kg === null ? 'No weigh-ins yet' : `${data.smoothed_kg} kg`}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Your goal</dt>
          <dd className="font-medium">{rateWords(data.expected_kg_per_week)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Recent trend</dt>
          <dd className="font-medium">
            {data.observed_kg_per_week === null
              ? 'Not enough weigh-ins yet'
              : rateWords(data.observed_kg_per_week)}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Calorie target</dt>
          <dd className="font-medium">{formatAmount(data.calorie_target_kcal, 'kcal')} kcal a day</dd>
        </div>
      </dl>
      {data.note !== null && <p className="mt-3 text-sm text-text-muted">{data.note}</p>}
    </Card>
  )
}

function Adjustment({ data }: { data: WeightTrend }) {
  if (data.adjustment === null) return null
  const { delta_kcal: delta, since, reason } = data.adjustment

  return (
    <Card>
      <CardTitle>Your calorie target moved</CardTitle>
      <p className="mt-1 text-sm">
        <strong className="font-medium">
          {delta > 0 ? '+' : ''}
          {delta} kcal
        </strong>{' '}
        since {formatDay(since)}.
      </p>
      <p className="mt-1 text-sm text-text-muted">{reason}</p>
    </Card>
  )
}

function TrendChart({ data }: { data: WeightTrend }) {
  return (
    <Card>
      <CardTitle>Trend</CardTitle>
      {data.weigh_ins.length < 2 ? (
        <p className="mt-2 text-sm text-text-muted">
          Your trend line appears after your second weigh-in.
        </p>
      ) : (
        // The list beside it carries the same figures for screen readers.
        <div className="mt-2 h-56 w-full" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.weigh_ins} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(iso: string) => formatDay(iso)}
                tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
                stroke="var(--color-border)"
              />
              <YAxis
                domain={['dataMin - 1', 'dataMax + 1']}
                tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 6,
                  color: 'var(--color-text)',
                }}
              />
              <Line
                type="monotone"
                dataKey="weight_kg"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function WeighInList({ data }: { data: WeightTrend }) {
  const remove = useRemoveWeighIn()
  const newestFirst = [...data.weigh_ins].reverse()

  return (
    <Card>
      <CardTitle>Weigh-ins</CardTitle>
      {newestFirst.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">No weigh-ins yet.</p>
      ) : (
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Every weigh-in, newest first</caption>
          <tbody className="divide-y divide-border">
            {newestFirst.map((weighIn) => (
              <tr key={weighIn.date}>
                <th scope="row" className="py-2 text-left font-normal">
                  {formatDay(weighIn.date)}
                </th>
                <td className="py-2">{weighIn.weight_kg} kg</td>
                <td className="py-2 text-right">
                  <Button
                    variant="quiet"
                    aria-label={`Remove the weigh-in on ${formatDay(weighIn.date)}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(weighIn.date)}
                  >
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          That weigh-in could not be removed. Please try again.
        </p>
      )}
    </Card>
  )
}

export function WeightScreen() {
  const weight = useWeight()

  if (weight.isPending) return <Skeleton className="h-64 w-full" />

  // A 404 means there is no profile yet: the trend starts from the profile's weight.
  if (weight.error instanceof ApiError && weight.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description="Your weight trend starts from the weight in your profile, so there is nothing to show until you have told us about yourself."
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
  if (weight.isError || weight.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your weight history could not be loaded. Please try again.
      </p>
    )
  }

  const data = weight.data
  return (
    <section className="space-y-4">
      <WeighInForm />
      <Summary data={data} />
      <Adjustment data={data} />
      <div className="grid gap-4 lg:grid-cols-2">
        <TrendChart data={data} />
        <WeighInList data={data} />
      </div>
    </section>
  )
}
```

- [ ] **Step 5: Run the tests and the checks**

Run: `npx vitest run && npx tsc -b && npm run lint`
Expected: all PASS and clean. No other test used the deleted weight handlers.

- [ ] **Step 6: Commit**

```bash
git add src/weight src/lib/format.ts src/lib/format.test.ts src/mocks/fixtures/more.ts \
  src/mocks/handlers/index.ts
git commit -m "feat(frontend): put the Weight screen on the real endpoint

A weigh-in now carries a date, so a missed week can be filled in, and is
checked against the profile's 20-300 kg bounds before it is sent; the field
clears only once the save succeeds. The screen shows the smoothed weight, the
goal's trajectory, the observed trend and today's calorie target, explains a
moved target and since when, and lists every weigh-in with a way to remove a
wrong one.

A weigh-in invalidates the profile as well as the targets, since it is the
profile's weight.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Frontend — the Cycle screen on the real endpoint

**Files:**
- Modify:
  - `src/cycle/types.ts`
  - `src/cycle/CycleScreen.tsx`
  - `src/cycle/CycleScreen.test.tsx`
  - `src/mocks/fixtures/more.ts`: `CYCLE_FIXTURE`
  - `src/mocks/handlers/index.ts`: delete the cycle handlers, and the fixture import if nothing is left using it
- Create: `src/cycle/useCycle.ts`, `src/cycle/CycleDayForm.tsx`, `src/cycle/ScreeningCard.tsx`

**Interfaces:**
- Consumes: the Task 8 contract, and `formatDay` from Task 9

- [ ] **Step 1: Write the contract as built**

Replace `src/cycle/types.ts`:

```ts
/**
 * CONTRACT for `/cycle` — plan 7.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec: the
 * screen can now log days with symptoms (coaching is symptom-driven, not
 * calendar-driven), answer the heavy-bleeding screening questions, and learn
 * that tracking is not offered to this profile at all.
 */

export type Flow = 'light' | 'medium' | 'heavy'

export const FLOWS: Flow[] = ['light', 'medium', 'heavy']

export const FLOW_LABELS: Record<Flow, string> = {
  light: 'Light',
  medium: 'Medium',
  heavy: 'Heavy',
}

/**
 * The symptoms the coaching responds to. There is deliberately no "cravings":
 * the perimenstrual chocolate-craving script is largely an American cultural
 * artefact, and has no place in the copy.
 */
export type Symptom = 'cramps' | 'bloating' | 'breast_tenderness' | 'low_mood'

export const SYMPTOMS: Symptom[] = ['cramps', 'bloating', 'breast_tenderness', 'low_mood']

export const SYMPTOM_LABELS: Record<Symptom, string> = {
  cramps: 'Cramps',
  bloating: 'Bloating',
  breast_tenderness: 'Breast tenderness',
  low_mood: 'Low mood',
}

export interface CycleDay {
  date: string
  /** Null on a day with symptoms but no bleeding. */
  flow: Flow | null
  symptoms: Symptom[]
}

export interface CycleDayInput {
  flow: Flow | null
  symptoms: Symptom[]
}

/**
 * How well supported a piece of advice is. Rendered as a visible label, because
 * the spec commits to evidence being "labelled, not laundered" — traditional
 * practice must never be presented as established nutrition.
 */
export type EvidenceGrade = 'strong' | 'moderate' | 'low' | 'traditional'

export interface CoachingNote {
  id: string
  title: string
  body: string
  evidence: EvidenceGrade
}

/** The validated heavy-bleeding screening questions. */
export interface ScreeningAnswers {
  soaks_within_two_hours: boolean
  longer_than_seven_days: boolean
  large_clots: boolean
  flooding: boolean
}

export interface Screening extends ScreeningAnswers {
  answered_on: string
}

export type IneligibleReason = 'not-female' | 'postmenopausal'

export interface CycleState {
  /** Tracking is offered to a woman's profile that is not postmenopausal. */
  eligible: boolean
  ineligible_reason: IneligibleReason | null
  /** Off unless the user turns it on, and private within a household by default. */
  enabled: boolean
  /** Something is stored, even while hidden, so it can still be erased. */
  has_history: boolean
  /** The first day of the latest logged bleed. Never a prediction. */
  last_period_start: string | null
  /** Logged days, newest first, the last 90 days. Empty while tracking is off. */
  days: CycleDay[]
  screening: Screening | null
  coaching: CoachingNote[]
  /**
   * Set when a screening answer is yes, or when more than seven consecutive days
   * of bleeding were logged. This produces a clinician referral and NEVER a
   * nutrient-target change: about 1 in 5 adolescents with heavy bleeding has an
   * underlying bleeding disorder, and answering with dietary advice would
   * suppress a real signal.
   */
  referral: { reason: string } | null
}
```

Replace `CYCLE_FIXTURE` in `src/mocks/fixtures/more.ts`:

```ts
export const CYCLE_FIXTURE: CycleState = {
  eligible: true,
  ineligible_reason: null,
  enabled: true,
  has_history: true,
  last_period_start: '2026-08-14',
  days: [
    { date: '2026-08-16', flow: 'medium', symptoms: [] },
    { date: '2026-08-15', flow: 'heavy', symptoms: ['cramps'] },
    { date: '2026-08-14', flow: 'medium', symptoms: ['bloating', 'cramps'] },
  ],
  screening: null,
  coaching: [
    {
      id: 'coffee-timing',
      title: 'Keep coffee and tea an hour away from meals',
      body: 'In young Indian women, one cup of tea with a rice meal cut iron absorption by about 49%, and two cups by about 67%. A one-hour gap roughly halves that.',
      evidence: 'strong',
    },
    {
      id: 'vitamin-c',
      title: 'Pair iron-rich meals with lemon, tomato, tamarind, amla or guava',
      body: 'Around your period, have something rich in vitamin C with the meal that carries your iron. This changes what to eat alongside, not how much iron you need.',
      evidence: 'moderate',
    },
    {
      id: 'ginger',
      title: 'Dry ginger (sukku), 750–2,000 mg a day on days 1–3',
      body: 'About half to one level teaspoon of dry ginger powder a day, on the first three days only. Painkillers such as ibuprofen still work better than any food. This is not a substitute for treatment.',
      evidence: 'moderate',
    },
    {
      id: 'calcium',
      title: 'Calcium at 1,000–1,200 mg a day',
      body: 'The only nutrient both ACOG and RCOG endorse for PMS. The trial took three cycles to show benefit, so give it time.',
      evidence: 'moderate',
    },
  ],
  referral: null,
}
```

In `src/mocks/handlers/index.ts`:
- delete the two `/cycle` handlers and the `// Plan 7 — weight and cycle.` comment;
- import only `REMINDERS_FIXTURE` from `../fixtures/more`;
- add "weight and cycle" to the list of real endpoints in the module comment.

- [ ] **Step 2: Write the failing tests**

Replace `src/cycle/CycleScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { CYCLE_FIXTURE } from '../mocks/fixtures/more'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { CycleScreen } from './CycleScreen'
import type { CycleState } from './types'

let patched: unknown = null
let saved: { date: string; body: unknown } | null = null
let answered: unknown = null
let cleared: string | null = null
let erased = false

function stubState(state: CycleState) {
  server.use(http.get(apiUrl('/cycle'), () => HttpResponse.json(state)))
}

// `/cycle` is a real endpoint now, so every request is stubbed here and nothing
// falls through to a default handler.
beforeEach(() => {
  patched = null
  saved = null
  answered = null
  cleared = null
  erased = false
  server.use(
    http.get(apiUrl('/cycle'), () => HttpResponse.json(CYCLE_FIXTURE)),
    http.patch(apiUrl('/cycle'), async ({ request }) => {
      patched = await request.json()
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
    http.delete(apiUrl('/cycle'), () => {
      erased = true
      return new HttpResponse(null, { status: 204 })
    }),
    http.put(apiUrl('/cycle/days/:date'), async ({ request, params }) => {
      saved = { date: params.date as string, body: await request.json() }
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
    http.delete(apiUrl('/cycle/days/:date'), ({ params }) => {
      cleared = params.date as string
      return new HttpResponse(null, { status: 204 })
    }),
    http.post(apiUrl('/cycle/screening'), async ({ request }) => {
      answered = await request.json()
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CycleScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const OFF: CycleState = { ...CYCLE_FIXTURE, enabled: false, days: [], coaching: [] }

test('is off until the user turns it on', async () => {
  stubState(OFF)
  renderScreen()

  expect(await screen.findByRole('switch', { name: /track my cycle/i })).not.toBeChecked()
  expect(screen.queryByText(/keep coffee and tea/i)).not.toBeInTheDocument()
})

test('turning it on sends the switch', async () => {
  stubState(OFF)
  renderScreen()

  await userEvent.click(await screen.findByRole('switch', { name: /track my cycle/i }))

  await waitFor(() => expect(patched).toEqual({ enabled: true }))
})

test('shows the coaching notes once enabled, with no demo banner', async () => {
  renderScreen()

  expect(await screen.findByText(/keep coffee and tea an hour away/i)).toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

/*
 * THE COUNTER-INTUITIVE RULE, LOCKED IN.
 *
 * ICMR's 29 mg/day iron figure for women ALREADY averages menstrual blood loss
 * across the whole cycle. Raising iron during a period double-counts the same
 * loss. The giveaway is that the pregnancy RDA (27 mg) is LOWER than the
 * non-pregnant one. This screen must therefore say the target does not move —
 * a future change that "helpfully" raises iron on bleed days breaks this test,
 * and `backend/tests/test_cycle_api.py` locks the number itself.
 */
test('states plainly that logging a period does not raise the iron target', async () => {
  renderScreen()

  expect(await screen.findByText(/iron target does not change/i)).toBeInTheDocument()
})

/*
 * The second locked rule. The luteal rise in resting expenditure is about 32
 * kcal/day once anovulatory cycles are accounted for — inside the noise of
 * day-to-day intake — and telling users the app expects them to eat more
 * manufactures exactly the logging pattern that would appear to validate it.
 */
test('states plainly that cycle phase does not change the calorie target', async () => {
  renderScreen()

  expect(await screen.findByText(/calorie target does not change/i)).toBeInTheDocument()
})

// Evidence is labelled, not laundered.
test('labels how strong the evidence behind each suggestion is', async () => {
  renderScreen()

  expect(await screen.findByText('Strong evidence')).toBeInTheDocument()
})

// Heavy bleeding gets a clinician, not a nutrient tweak: roughly 1 in 5
// adolescents with heavy bleeding has an underlying bleeding disorder.
test('refers heavy bleeding to a clinician rather than adjusting nutrients', async () => {
  stubState({
    ...CYCLE_FIXTURE,
    referral: { reason: 'You reported soaking through a pad or tampon in two hours or less.' },
  })
  renderScreen()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(/clinician/i)
  expect(alert).toHaveTextContent(/soaking through a pad/i)
  expect(alert).toHaveTextContent(/adolescents/i)
})

test('is not offered to a male profile, and says why', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'not-female' })
  renderScreen()

  expect(await screen.findByText(/for profiles set to female/i)).toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
})

test('after menopause, says any bleeding should be checked by a clinician', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'postmenopausal' })
  renderScreen()

  expect(await screen.findByText(/should be checked by a clinician/i)).toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
})

test('logs a day with its flow and symptoms', async () => {
  renderScreen()

  await userEvent.selectOptions(await screen.findByLabelText('Bleeding'), 'heavy')
  await userEvent.click(screen.getByRole('checkbox', { name: 'Cramps' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save day' }))

  await waitFor(() =>
    expect(saved).toEqual({ date: todayIso(), body: { flow: 'heavy', symptoms: ['cramps'] } }),
  )
})

test('will not save a day with nothing in it', async () => {
  renderScreen()

  expect(await screen.findByRole('button', { name: 'Save day' })).toBeDisabled()
})

test('sends the screening answers', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('checkbox', { name: /soak through a pad/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Save answers' }))

  await waitFor(() =>
    expect(answered).toEqual({
      soaks_within_two_hours: true,
      longer_than_seven_days: false,
      large_clots: false,
      flooding: false,
      date: todayIso(),
    }),
  )
})

test('shows when the last period started, from logged days only', async () => {
  renderScreen()

  expect(await screen.findByText(/last period started on 14 Aug 2026/i)).toBeInTheDocument()
  expect(screen.getByText(/heavy flow, cramps/i)).toBeInTheDocument()
})

test('a logged day can be removed', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove 16 Aug 2026' }))

  await waitFor(() => expect(cleared).toBe('2026-08-16'))
})

test('deleting the history asks first', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Delete my cycle history' }))
  expect(erased).toBe(false)

  await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))
  await waitFor(() => expect(erased).toBe(true))
})

test('history hidden by a profile change can still be erased', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'postmenopausal', has_history: true })
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Delete my cycle history' }))
  await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))
  await waitFor(() => expect(erased).toBe(true))
})

test('offers no erase when nothing is stored', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'not-female', has_history: false })
  renderScreen()

  await screen.findByText(/for profiles set to female/i)
  expect(screen.queryByRole('button', { name: 'Delete my cycle history' })).not.toBeInTheDocument()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(http.get(apiUrl('/cycle'), () => new HttpResponse('no profile', { status: 404 })))
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
})
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npx vitest run src/cycle`
Expected: FAIL. The screen has no eligibility states, no day form and no screening, and it still renders the banner.

- [ ] **Step 4: Implement the hooks and the two cards**

Create `src/cycle/useCycle.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { CycleDayInput, CycleState, ScreeningAnswers } from './types'

/** `date` is the user's today: coaching such as "days 1–3" is read against it. */
export function useCycle(date: string) {
  return useQuery({
    queryKey: ['cycle', date],
    queryFn: () => api.get<CycleState>(`/cycle?date=${date}`),
    retry: false,
  })
}

function useCycleMutation<TVariables>(mutationFn: (variables: TVariables) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cycle'] }),
  })
}

export function useSetCycleEnabled() {
  return useCycleMutation((enabled: boolean) => api.patch('/cycle', { enabled }))
}

export function useSaveCycleDay() {
  return useCycleMutation(({ date, day }: { date: string; day: CycleDayInput }) =>
    api.put(`/cycle/days/${date}`, day),
  )
}

export function useClearCycleDay() {
  return useCycleMutation((date: string) => api.del(`/cycle/days/${date}`))
}

export function useSaveScreening() {
  return useCycleMutation((answers: ScreeningAnswers & { date: string }) =>
    api.post('/cycle/screening', answers),
  )
}

export function useEraseCycle() {
  return useCycleMutation<void>(() => api.del('/cycle'))
}
```

Create `src/cycle/CycleDayForm.tsx`:

```tsx
import { useState } from 'react'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox, Field, Select, TextInput } from '../ui/fields'
import { FLOWS, FLOW_LABELS, SYMPTOMS, SYMPTOM_LABELS } from './types'
import type { Flow, Symptom } from './types'
import { useSaveCycleDay } from './useCycle'

/**
 * One day at a time: bleeding (or none) and symptoms. A symptom can be logged on
 * a day without bleeding, because PMS comes before a period, not during it.
 */
export function CycleDayForm() {
  const save = useSaveCycleDay()
  const [date, setDate] = useState(todayIso)
  const [flow, setFlow] = useState<Flow | ''>('')
  const [symptoms, setSymptoms] = useState<Symptom[]>([])

  const empty = flow === '' && symptoms.length === 0

  function toggle(symptom: Symptom, checked: boolean) {
    setSymptoms((current) =>
      checked ? [...current, symptom] : current.filter((item) => item !== symptom),
    )
  }

  return (
    <Card>
      <CardTitle>Log a day</CardTitle>
      <div className="mt-2 grid gap-x-3 sm:grid-cols-2">
        <Field label="Date">
          {(props) => (
            <TextInput
              {...props}
              type="date"
              value={date}
              max={todayIso()}
              onChange={(event) => setDate(event.target.value)}
            />
          )}
        </Field>
        <Field label="Bleeding">
          {(props) => (
            <Select
              {...props}
              value={flow}
              onChange={(event) => setFlow(event.target.value as Flow | '')}
            >
              <option value="">None</option>
              {FLOWS.map((item) => (
                <option key={item} value={item}>
                  {FLOW_LABELS[item]}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Symptoms</legend>
        {SYMPTOMS.map((symptom) => (
          <Checkbox
            key={symptom}
            label={SYMPTOM_LABELS[symptom]}
            checked={symptoms.includes(symptom)}
            onChange={(event) => toggle(symptom, event.target.checked)}
          />
        ))}
      </fieldset>
      <Button
        variant="primary"
        className="mt-3"
        disabled={empty || date === '' || save.isPending}
        onClick={() =>
          save.mutate(
            { date, day: { flow: flow === '' ? null : flow, symptoms } },
            {
              onSuccess: () => {
                setFlow('')
                setSymptoms([])
              },
            },
          )
        }
      >
        Save day
      </Button>
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          That day could not be saved. Please try again.
        </p>
      )}
    </Card>
  )
}
```

Create `src/cycle/ScreeningCard.tsx`:

```tsx
import { useState } from 'react'
import { formatDay } from '../lib/format'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox } from '../ui/fields'
import type { Screening, ScreeningAnswers } from './types'
import { useSaveScreening } from './useCycle'

/*
 * The validated heavy-bleeding questions. A yes to any of them produces a
 * clinician referral — never a nutrient change. Flow logged as "heavy" is not
 * one of them: a self-rating is not a screening question.
 */
const QUESTIONS: { field: keyof ScreeningAnswers; label: string }[] = [
  {
    field: 'soaks_within_two_hours',
    label: 'Do you soak through a pad or tampon in two hours or less?',
  },
  { field: 'longer_than_seven_days', label: 'Does your period usually last more than seven days?' },
  { field: 'large_clots', label: 'Do you pass clots larger than a ₹10 coin (about 2.5 cm)?' },
  {
    field: 'flooding',
    label: 'Do you have flooding — bleeding through to your clothes or bedding?',
  },
]

function answersOf(saved: Screening | null): ScreeningAnswers {
  return {
    soaks_within_two_hours: saved?.soaks_within_two_hours ?? false,
    longer_than_seven_days: saved?.longer_than_seven_days ?? false,
    large_clots: saved?.large_clots ?? false,
    flooding: saved?.flooding ?? false,
  }
}

export function ScreeningCard({ saved }: { saved: Screening | null }) {
  const save = useSaveScreening()
  const [answers, setAnswers] = useState(() => answersOf(saved))

  return (
    <Card>
      <CardTitle>Heavy bleeding check</CardTitle>
      <p className="mt-1 text-sm text-text-muted">
        Four questions clinicians use to spot bleeding that needs looking into. A yes to any of
        them means seeing a clinician. It never changes a nutrient target.
      </p>
      <div className="mt-2">
        {QUESTIONS.map(({ field, label }) => (
          <Checkbox
            key={field}
            label={label}
            checked={answers[field]}
            onChange={(event) =>
              setAnswers((current) => ({ ...current, [field]: event.target.checked }))
            }
          />
        ))}
      </div>
      {saved !== null && (
        <p className="text-xs text-text-muted">Last answered {formatDay(saved.answered_on)}.</p>
      )}
      <Button
        className="mt-3"
        disabled={save.isPending}
        onClick={() => save.mutate({ ...answers, date: todayIso() })}
      >
        Save answers
      </Button>
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          Your answers could not be saved. Please try again.
        </p>
      )}
    </Card>
  )
}
```

- [ ] **Step 5: Rebuild the screen**

Replace `src/cycle/CycleScreen.tsx`:

```tsx
import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { formatDay } from '../lib/format'
import { todayIso } from '../today/useToday'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import { CycleDayForm } from './CycleDayForm'
import { ScreeningCard } from './ScreeningCard'
import { FLOW_LABELS, SYMPTOM_LABELS } from './types'
import type { CycleDay, CycleState, EvidenceGrade, IneligibleReason } from './types'
import { useClearCycleDay, useCycle, useEraseCycle, useSetCycleEnabled } from './useCycle'

const EVIDENCE_LABELS: Record<EvidenceGrade, string> = {
  strong: 'Strong evidence',
  moderate: 'Moderate evidence',
  low: 'Low-quality evidence',
  // Never presented as established nutrition.
  traditional: 'Traditional practice, not established nutrition',
}

const PROFILE_LINK =
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface'

function NotOffered({ reason }: { reason: IneligibleReason | null }) {
  const action = (
    <Link to="/profile/about" className={PROFILE_LINK}>
      Review your profile
    </Link>
  )
  if (reason === 'postmenopausal') {
    return (
      <EmptyState
        title="Cycle tracking is for women who have periods"
        description="Your profile says you no longer have periods, so your iron target uses the IOM figure for women after menopause. Any bleeding after menopause should be checked by a clinician."
        action={action}
      />
    )
  }
  return (
    <EmptyState
      title="Cycle tracking is for profiles set to female"
      description="The sex on your profile chooses which ICMR reference values apply, so change it only if it is wrong."
      action={action}
    />
  )
}

function describeDay(day: CycleDay): string {
  const bleeding = day.flow === null ? 'no bleeding' : `${FLOW_LABELS[day.flow].toLowerCase()} flow`
  return [bleeding, ...day.symptoms.map((symptom) => SYMPTOM_LABELS[symptom].toLowerCase())].join(
    ', ',
  )
}

function RecentDays({ data }: { data: CycleState }) {
  const clear = useClearCycleDay()

  return (
    <Card>
      <CardTitle>Recent days</CardTitle>
      {data.last_period_start !== null && (
        <p className="mt-1 text-sm text-text-muted">
          Your last period started on {formatDay(data.last_period_start)}.
        </p>
      )}
      {data.days.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">Nothing logged in the last 90 days.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {data.days.map((day) => (
            <li key={day.date} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>
                <span className="font-medium">{formatDay(day.date)}</span> — {describeDay(day)}
              </span>
              <Button
                variant="quiet"
                aria-label={`Remove ${formatDay(day.date)}`}
                disabled={clear.isPending}
                onClick={() => clear.mutate(day.date)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function EraseHistory() {
  const erase = useEraseCycle()
  const [confirming, setConfirming] = useState(false)

  return (
    <Card>
      <CardTitle>Your cycle history</CardTitle>
      <p className="mt-1 text-sm text-text-muted">
        Private to you, even in a household, unless you choose to share your health details.
      </p>
      {confirming ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm">
            This deletes every day, symptom and answer you have logged, and turns tracking off.
            It cannot be undone.
          </p>
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={erase.isPending}
              onClick={() => erase.mutate(undefined, { onSuccess: () => setConfirming(false) })}
            >
              Delete everything
            </Button>
            <Button onClick={() => setConfirming(false)}>Keep it</Button>
          </div>
        </div>
      ) : (
        <Button variant="danger" className="mt-3" onClick={() => setConfirming(true)}>
          Delete my cycle history
        </Button>
      )}
    </Card>
  )
}

export function CycleScreen() {
  const cycle = useCycle(todayIso())
  const setEnabled = useSetCycleEnabled()

  if (cycle.isPending) return <Skeleton className="h-64 w-full" />
  if (cycle.error instanceof ApiError && cycle.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your profile"
        description="Whether cycle tracking applies depends on your profile, so there is nothing to show until you have told us about yourself."
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }
  if (cycle.isError || cycle.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Cycle tracking could not be loaded. Please try again.
      </p>
    )
  }

  const data = cycle.data
  if (!data.eligible) {
    // Data logged before a profile change is hidden, but must stay erasable.
    return (
      <section className="space-y-4">
        <NotOffered reason={data.ineligible_reason} />
        {data.has_history && <EraseHistory />}
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <Card>
        <Toggle
          label="Track my cycle"
          description="Off by default, and private within a household unless you choose to share it."
          checked={data.enabled}
          onChange={(checked) => setEnabled.mutate(checked)}
        />
      </Card>

      {data.enabled && (
        <>
          {data.referral !== null && (
            <div
              role="alert"
              className="flex gap-2 rounded-card border border-above-limit/40 bg-above-limit/5 p-3 text-sm text-above-limit"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>
                <strong className="font-medium">Please see a clinician.</strong>{' '}
                {data.referral.reason} Heavy bleeding needs medical assessment — around one in
                five adolescents with it has an underlying bleeding disorder. This is not
                something to address with food.
              </span>
            </div>
          )}

          {/*
            These two statements are load-bearing, not reassurance. Both features
            are the intuitive design and both are wrong, so the app says out loud
            what it does NOT do.
          */}
          <Card>
            <CardTitle>What this does and doesn’t change</CardTitle>
            <ul className="mt-2 space-y-2 text-sm text-text-muted">
              <li>
                Your <strong className="text-text">iron target does not change</strong> when you
                log a period. The ICMR figure for women already averages menstrual loss across
                the whole cycle, so raising it would count the same loss twice — and your body
                already absorbs more iron during menses.
              </li>
              <li>
                Your <strong className="text-text">calorie target does not change</strong> with
                cycle phase. The real luteal increase is around 32 kcal a day once anovulatory
                cycles are accounted for, which is far inside normal day-to-day variation.
              </li>
              <li>
                What does change is coaching: when to take coffee or tea, and what to pair an
                iron-rich meal with. It follows the days and symptoms you log, never a predicted
                calendar.
              </li>
            </ul>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <CycleDayForm />
            {/* Keyed on the saved answers, so the boxes reset when they change. */}
            <ScreeningCard
              key={data.screening?.answered_on ?? 'none'}
              saved={data.screening}
            />
          </div>

          <RecentDays data={data} />

          <Card>
            <CardTitle>Around your period</CardTitle>
            <ul className="mt-2 space-y-4">
              {data.coaching.map((note) => (
                <li key={note.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{note.title}</p>
                    <Badge tone={note.evidence === 'strong' ? 'accent' : 'neutral'}>
                      {EVIDENCE_LABELS[note.evidence]}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-sm text-text-muted">{note.body}</p>
                </li>
              ))}
            </ul>
          </Card>

          <EraseHistory />
        </>
      )}
      {!data.enabled && data.has_history && <EraseHistory />}
    </section>
  )
}
```

- [ ] **Step 6: Run the tests and the checks**

Run: `npx vitest run && npx tsc -b && npm run lint`
Expected: all PASS and clean.

- [ ] **Step 7: Commit**

```bash
git add src/cycle src/mocks/fixtures/more.ts src/mocks/handlers/index.ts
git commit -m "feat(frontend): put the Cycle screen on the real endpoint

The screen can now do what the spec asks of it: log a day's bleeding and
symptoms, answer the four heavy-bleeding screening questions, remove a day,
and erase the whole history after a confirmation. It says plainly when
tracking is not offered -- to a male profile, or after menopause, where any
bleeding should be checked by a clinician.

The referral copy now says 'adolescents', which is what the evidence says,
rather than 'people'.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---
## Task 11: Frontend — the periods question, and Today's new warnings

**Files:**
- Modify:
  - `src/onboarding/types.ts`, `src/onboarding/validation.ts`, `src/onboarding/steps.tsx`, `src/onboarding/useProfile.ts`
  - `src/onboarding/OnboardingWizard.tsx`: a save also refreshes weight and cycle
  - `src/profile/ProfileScreen.tsx`
  - `src/today/types.ts`, `src/today/TodayScreen.tsx`
  - Every `SavedProfile` fixture. Run `grep -rn "cereal_dominant" src --include='*.test.*'` to find them; they include `src/profile/ProfileScreen.test.tsx` and `src/onboarding/useProfile.test.ts`.
- Test: `src/onboarding/validation.test.ts`, `src/onboarding/useProfile.test.ts`, `src/onboarding/OnboardingWizard.test.tsx`, `src/profile/ProfileScreen.test.tsx`, `src/today/TodayScreen.test.tsx` (append to each)

**Interfaces:**
- Consumes: `menstrual_status` on `GET/PUT /profile` (Task 6); the warning kinds `calorie-recalibrated`, `reference-framework` and `approaching-limit` (Tasks 4 and 6)
- Produces:
  - `type MenstrualStatus = 'menstruating' | 'postmenopausal'`
  - `MENSTRUAL_STATUS_LABELS`
  - `OnboardingAnswers.menstrual_status: MenstrualStatus | null`
  - `SavedProfile.menstrual_status`

- [ ] **Step 1: Write the failing tests**

Append to `src/onboarding/validation.test.ts`:

```ts
// ICMR's 29 mg iron figure for women averages menstrual loss; after menopause a
// different figure applies. So a woman is asked, and a man is not.
test('a woman is asked whether she still has periods', () => {
  expect(
    validateStep(
      'about',
      answers({ sex: 'female', age: '52', weight_kg: '60', activity: 'moderate' }),
    ),
  ).toMatch(/periods/i)
})

test('a woman who answers it may continue', () => {
  expect(
    validateStep(
      'about',
      answers({
        sex: 'female',
        age: '52',
        weight_kg: '60',
        activity: 'moderate',
        menstrual_status: 'postmenopausal',
      }),
    ),
  ).toBeNull()
})

test('a man is not asked about periods', () => {
  expect(
    validateStep('about', answers({ sex: 'male', age: '34', weight_kg: '74.2', activity: 'moderate' })),
  ).toBeNull()
})
```

Append to `src/onboarding/useProfile.test.ts`:

```ts
// Carried explicitly: PUT /profile replaces rather than merges, so a status left
// out here would be wiped by the next save of any other section.
test('the menstrual status is carried into the wizard state', () => {
  const answers = answersFromProfile(
    savedProfile({ sex: 'female', menstrual_status: 'postmenopausal' }),
  )
  expect(answers.menstrual_status).toBe('postmenopausal')
})
```

In that file's `savedProfile()` default object, add `menstrual_status: null,` after `cereal_dominant: false,`.

Append to `src/onboarding/OnboardingWizard.test.tsx`:

```tsx
test('asks about periods only once Female is chosen', async () => {
  await renderWizard()

  expect(screen.queryByLabelText(/still have periods/i)).not.toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'female')
  expect(screen.getByLabelText(/still have periods/i)).toBeInTheDocument()

  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'male')
  expect(screen.queryByLabelText(/still have periods/i)).not.toBeInTheDocument()
})
```

In `src/profile/ProfileScreen.test.tsx`, add `menstrual_status: 'postmenopausal',` to `PROFILE` after `cereal_dominant: true,`, and append:

```tsx
test('shows whether a woman still has periods', async () => {
  renderScreen()

  const about = await screen.findByRole('region', { name: 'About you' })
  expect(within(about).getByText('Periods')).toBeInTheDocument()
  expect(within(about).getByText(/past menopause/i)).toBeInTheDocument()
})
```

(Add `within` to that file's `@testing-library/react` import.)

Append to `src/today/TodayScreen.test.tsx`:

```tsx
test('explains a recalibrated calorie target and a non-ICMR iron figure', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () =>
      HttpResponse.json({
        ...TODAY_FIXTURE,
        warnings: [
          {
            kind: 'calorie-recalibrated',
            message: 'Your calorie target is 210 kcal lower than the formula gives, because your weigh-ins have drifted from your goal. The Weight screen has the detail.',
          },
          {
            kind: 'reference-framework',
            message: 'Your iron target is 8 mg, the IOM figure for women after menopause.',
          },
        ],
      }),
    ),
  )
  renderScreen()

  expect(await screen.findByText(/210 kcal lower than the formula/)).toBeInTheDocument()
  expect(screen.getByText(/the IOM figure for women after menopause/)).toBeInTheDocument()
})

// Two warnings of one kind are two warnings, not one rendered twice under one key.
test('shows every warning, even two of the same kind', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () =>
      HttpResponse.json({
        ...TODAY_FIXTURE,
        warnings: [
          { kind: 'drug-interaction', message: 'First interaction.' },
          { kind: 'drug-interaction', message: 'Second interaction.' },
        ],
      }),
    ),
  )
  renderScreen()

  expect(await screen.findByText('First interaction.')).toBeInTheDocument()
  expect(screen.getByText('Second interaction.')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run src/onboarding src/profile src/today`
Expected: FAIL. There is no periods question, `menstrual_status` is not carried, and `tsc` rejects the new `WarningKind` values in the fixtures.

- [ ] **Step 3: Implement the question**

In `src/onboarding/types.ts`, after `DietType`, add:

```ts
/**
 * Asked of women only. ICMR's 29 mg iron figure for women averages menstrual
 * loss; ICMR publishes no postmenopausal category, so after menopause the IOM
 * figure applies instead, with a note on Today saying so.
 */
export type MenstrualStatus = 'menstruating' | 'postmenopausal'
```

and after `SEX_LABELS`:

```ts
export const MENSTRUAL_STATUS_LABELS: Record<MenstrualStatus, string> = {
  menstruating: 'Yes, I have periods',
  postmenopausal: 'No, I am past menopause',
}
```

In `OnboardingAnswers`, after `sex`, add:

```ts
  /** Null for a man, and until a woman answers. */
  menstrual_status: MenstrualStatus | null
```

In `src/onboarding/validation.ts`:
- add `menstrual_status: null,` to `emptyAnswers()` after `sex: null,`;
- in the `'about'` case, directly after the sex check, add:

```ts
      if (answers.sex === 'female' && answers.menstrual_status === null) {
        return 'Please say whether you still have periods — it decides which iron figure applies.'
      }
```

In `src/onboarding/steps.tsx`, import `MENSTRUAL_STATUS_LABELS` and the `MenstrualStatus` type alongside the others. Change the Sex select's `onChange` so a switch to male clears the answer:

```tsx
            onChange={(event) => {
              const sex = event.target.value as Sex
              // A status only means something on a woman's profile; leaving one
              // behind would come back if the profile were switched again.
              update({ sex, menstrual_status: sex === 'female' ? answers.menstrual_status : null })
            }}
```

Then add, directly after the Sex `Field`:

```tsx
      {answers.sex === 'female' && (
        <Field
          label="Do you still have periods?"
          hint="ICMR’s iron figure for women averages menstrual loss. After menopause a lower figure applies."
        >
          {(props) => (
            <Select
              {...props}
              value={answers.menstrual_status ?? ''}
              onChange={(event) =>
                update({ menstrual_status: event.target.value as MenstrualStatus })
              }
            >
              <option value="" disabled>
                Choose…
              </option>
              {Object.entries(MENSTRUAL_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
```

In `src/onboarding/useProfile.ts`:
- add `menstrual_status: OnboardingAnswers['menstrual_status']` to `SavedProfile` after `sex`;
- in `answersFromProfile`, add `menstrual_status: profile.menstrual_status ?? null,` after `sex: profile.sex,`.

In `src/onboarding/OnboardingWizard.tsx`, extend `useSaveProfile`'s `onSuccess`:

```ts
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      // First targets are computed from the profile, so they change too.
      queryClient.invalidateQueries({ queryKey: ['targets'] })
      // A changed weight is a weigh-in, and a changed goal resets a recalibration.
      queryClient.invalidateQueries({ queryKey: ['weight'] })
      // Sex and menstrual status decide whether cycle tracking is offered at all.
      queryClient.invalidateQueries({ queryKey: ['cycle'] })
    },
```

In `src/profile/ProfileScreen.tsx`, import `MENSTRUAL_STATUS_LABELS` and `MenstrualStatus`. In the About section, after the Sex row, add:

```tsx
            {data.sex === 'female' && (
              <SummaryRow label="Periods">
                {data.menstrual_status === null ? (
                  <NotSet />
                ) : (
                  MENSTRUAL_STATUS_LABELS[data.menstrual_status as MenstrualStatus]
                )}
              </SummaryRow>
            )}
```

- [ ] **Step 4: Teach Today the new warnings**

In `src/today/types.ts`:
- replace the stale reference to `src/mocks/handlers/targets.ts` in the top comment with "Implemented by the backend's `app/targets/router.py`.";
- replace `WarningKind` and its comment with:

```ts
/**
 * Day-level notes from `resolve_day`. `above-limit` is not one of them — it is a
 * per-nutrient status, not a day-level warning — and is kept out for that reason.
 *
 * - `calorie-recalibrated`: weigh-ins moved the energy target off the formula.
 * - `reference-framework`: iron is the IOM figure after menopause, not ICMR's.
 * - `approaching-limit`: after menopause, a day's iron is near the upper limit.
 */
export type WarningKind =
  | 'condition-conflict'
  | 'medication-timing'
  | 'drug-interaction'
  | 'calorie-recalibrated'
  | 'reference-framework'
  | 'approaching-limit'
```

In `src/today/TodayScreen.tsx`:
- give `approaching-limit` the alarm styling that a conflict has. In `WarningNote`, replace `const conflict = warning.kind === 'condition-conflict'` with:

```ts
  // Both need acting on rather than noting: a conflict goes to a clinician, and
  // iron near its limit after menopause has no route out of the body.
  const conflict = warning.kind === 'condition-conflict' || warning.kind === 'approaching-limit'
```

- change the warnings list's key to `key={`${warning.kind}-${index}`}`, taking `index` from the `map` callback.

- [ ] **Step 5: Run the tests and the checks**

Run: `npx vitest run && npx tsc -b && npm run lint`
Expected: all PASS and clean. If `tsc` names a `SavedProfile` literal without `menstrual_status`, add `menstrual_status: null` to it.

- [ ] **Step 6: Commit**

```bash
git add src/onboarding src/profile src/today
git commit -m "feat(frontend): ask women whether they still have periods, and show Today's new notes

The About step asks the question only once Female is chosen, and clears it
if the answer changes to Male; the profile summary reads it back, and the
wizard carries it through every section edit so a save of anything else
cannot wipe it. A profile save now also refreshes the weight and cycle
screens, since it can record a weigh-in or change who cycle tracking is for.

Today knows the three new warning kinds, styles iron near its limit as the
alarm it is, and keys warnings by position so two of one kind both show.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: End-to-end walks, READMEs, and the plan record

**Files:**
- Modify:
  - `frontend/e2e/smoke.spec.ts`: append two tests and update the header comment
  - `frontend/playwright.config.ts`: `use.timezoneId`, so the browser's date is the e2e user's date
  - `frontend/README.md`
  - `docs/superpowers/plans/README.md`
  - `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`: the contract table
  - this file

- [ ] **Step 1: Append the Playwright walks**

Both need the profile the first test creates, and `globalSetup` resets the user once per run. They therefore belong at the end of the existing `test.describe('the tracking loop', ...)` block, after the swap-and-lock test. The cycle walk switches the profile to female, so it must be last.

```ts
  test('a weigh-in lands in the list and becomes the profile weight', async ({ page }) => {
    await page.goto('/weight')
    await expect(page.getByRole('heading', { name: 'Where you are' })).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Onboarding recorded the first weigh-in, from the profile's 65 kg.
    await expect(page.getByRole('cell', { name: '65 kg' })).toBeVisible()

    await page.getByLabel(/weight in kg/i).fill('64.5')
    await page.getByRole('button', { name: 'Save', exact: true }).click()

    // Same day, so it replaces the onboarding weigh-in rather than joining it.
    await expect(page.getByRole('cell', { name: '64.5 kg' })).toBeVisible()
    await expect(page.getByRole('cell', { name: '65 kg' })).toHaveCount(0)

    await page.goto('/profile')
    await expect(page.getByText('64.5 kg')).toBeVisible()
  })

  test('cycle tracking is offered to a woman who menstruates, and heavy bleeding refers', async ({
    page,
  }) => {
    await page.goto('/cycle')
    // The walk onboarded a man.
    await expect(page.getByText(/cycle tracking is for profiles set to female/i)).toBeVisible()

    // Switch the profile through the real API: the wizard itself is walked above.
    const api = 'http://localhost:8000'
    const profile = await (await page.request.get(`${api}/profile`)).json()
    const saved = await page.request.put(`${api}/profile`, {
      data: { ...profile, sex: 'female', weight_kg: 55, menstrual_status: 'menstruating' },
    })
    expect(saved.ok()).toBe(true)

    await page.reload()
    const toggle = page.getByRole('switch', { name: /track my cycle/i })
    await expect(toggle).not.toBeChecked()
    // The switch shows the server's state and turns on only once the PATCH and the
    // refetch land, so check()'s one-time state read would throw. Click, then wait.
    await toggle.click()
    await expect(toggle).toBeChecked()
    await expect(page.getByText(/iron target does not change/i)).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Exact: the flooding question's label also contains "bleeding".
    await page.getByLabel('Bleeding', { exact: true }).selectOption('heavy')
    await page.getByRole('checkbox', { name: 'Cramps' }).check()
    await page.getByRole('button', { name: 'Save day' }).click()
    await expect(page.getByText(/heavy flow, cramps/i)).toBeVisible()

    await page.getByRole('checkbox', { name: /soak through a pad/i }).check()
    await page.getByRole('button', { name: 'Save answers' }).click()
    await expect(page.getByRole('alert')).toContainText(/please see a clinician/i)
  })
```

Add two bullets to the header comment list:
- "Weight on the real trend: onboarding's weight is the first weigh-in, and a weigh-in the same day replaces it."
- "Cycle tracking gated on the profile, and a heavy-bleeding answer producing a referral rather than a changed target."

Then, in `frontend/playwright.config.ts`, add inside the top-level `use: { ... }` block:

```ts
    // The browser's date must be the e2e user's. The weight walk compares a weigh-in
    // the browser dates (`todayIso()`) with the one onboarding recorded, which the
    // server dates in the user's zone -- Asia/Kolkata, set in
    // backend/scripts/e2e_session.py. On a UTC CI runner they differ from 18:30 UTC.
    timezoneId: 'Asia/Kolkata',
```

- [ ] **Step 2: Run it against the real stack**

From the repo root, with Postgres up (`docker compose up -d db`):

```bash
cd backend && uv run python -m scripts.e2e_seed
cd backend && (uv run uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &) && sleep 3 && curl -sf http://localhost:8000/health
cd frontend && npm run test:e2e
```

Expected: `7 passed`, or `6 passed, 1 skipped` where the database has no slot-tagged dishes. Stop the API afterwards with `pkill -f "uvicorn app.main:app --port 8000"`.

- [ ] **Step 3: Update the frontend README**

In `frontend/README.md`, under "Which screens are real", replace the two paragraphs with:

> **Live against the real backend:** sign-in, household, food search, the onboarding questionnaire and profile, Today (real ICMR-NIN targets and the compensation ledger), meal logging, the meal plan (generation, swap, lock, regenerate, and the household cooking view), weight (weigh-ins, the trend and calorie recalibration) and cycle tracking.
>
> **Still on MSW fixtures:** Report and Reminders. Each carries a **Demo data** banner naming the endpoint it is waiting for. Those handlers and the `types.ts` in each feature folder are the proposed contract for the remaining backend plans.

Make three more replacements:
- "Auth, households and food search talk to the real FastAPI backend" → "Every screen but Report and Reminders talks to the real FastAPI backend".
- "Most screens are not wired to a backend yet (see below)" → "Report and Reminders are not wired to a backend yet (see below)".
- Under "End to end", "Playwright: onboarding -> log -> dashboard, then the plan" → "Playwright: onboarding -> log -> dashboard, then the plan, weight and cycle".

- [ ] **Step 4: Update the contract table, the plans index and this file's status**

In `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`, replace the two plan 7 rows of the contract table with:

```
| `GET/POST /weight`, `DELETE /weight/{date}` | `src/weight/types.ts` | Plan 7 (built; contract amended) |
| `GET/PATCH/DELETE /cycle`, `PUT/DELETE /cycle/days/{date}`, `POST /cycle/screening` | `src/cycle/types.ts` | Plan 7 (built; contract amended) |
```

In `docs/superpowers/plans/README.md`, change row 7 to:

`| 7 | Weight & cycle | Weigh-ins, trend smoothing, calorie recalibration, cycle logging and coaching | **Complete** — `2026-09-24-weight-and-cycle.md`. Recalibration is evaluated when a weigh-in is posted rather than on a schedule; postmenopausal status and the IOM iron fallback live on the profile |`

Then, after the paragraph about plan 6, add: "Plan 7's decisions and the gaps it leaves are recorded at the top and bottom of `2026-09-24-weight-and-cycle.md`."

In this file, add a `**Status:**` line under the Spec paragraph at the top. Use the form the other plans use: the test counts from the final run, and the checks that passed.

- [ ] **Step 5: Run everything**

```bash
cd backend  && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npx vitest run && npx tsc -b && npm run lint && npm run build
```

Expected: every command clean. Record the counts in the Status line.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e frontend/playwright.config.ts frontend/README.md docs/superpowers/plans/README.md \
  docs/superpowers/plans/2026-09-24-weight-and-cycle.md \
  docs/superpowers/specs/2026-08-17-ui-foundation-design.md
git commit -m "docs: record plan 7, weight and cycle, and add its end-to-end walks

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Known gaps to record in the closeout

- **Recalibration runs only when a weigh-in is posted.** A user who stops weighing in keeps the last step indefinitely. A scheduled re-read belongs with plan 8's job runner.
- **The ledger re-costs the window against the target date's targets.** `resolve_day` builds one set of targets and uses it for the four days before the target date. On the first days after a step, the earlier days' carries are therefore costed against the new target. This was already the case for every profile change.
- **Pregnancy and lactation are not modelled.** There is no reference row for them, and the iron upper limit's pregnancy exception is not applied.
- **Adolescents get the adult reference rows.** The heavy-bleeding referral's 1-in-5 figure is specifically about adolescents, which is why the referral does not depend on age. The targets for under-18s are still the adult ones.
- **Weight and cycle are private because nothing exposes them, not because a permission is checked.** `share_health` is still read by nothing. The first endpoint that shows one member's health data to another must read it.
- **60+ targets are still thin, for men and women alike.** The 60+ band carries four nutrients (protein, calcium, iron and vitamin D), and protein is computed anyway. This plan added the missing iron note, but not the fourteen nutrients the band lacks, which need a decision on falling back to the 18–59 figures.
- **A step does not re-size this week's stored plan.** Regenerating would throw away the user's swaps, so the Plan screen's Regenerate is left to do it. A hint on the Plan screen when the target has moved since the week was planned would close the gap.
- **No approaching-limit warning for anyone but postmenopausal women.** The planner still penalises only going over a TUL.
- **The oxalate class and the whole-versus-hulled sesame split are still not used.** Both matter to the calcium coaching. The coaching names calcium; the food scoring does not yet discount high-oxalate greens.
