# Weekly Report & Reminders Implementation Plan (plan 8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real weekly report — what was hit, what was missed and could not be made up, how much was estimated, and what to eat next week, feeding the next plan — and browser push reminders at each meal slot that stop once the slot is logged. These replace the last two MSW fixtures, Report and Reminders.

**Architecture:**
- The compensation ledger's walk moves out of `resolve_day` into one reusable `walk_ledger`. The walk records what each day carried, and what expired, and in which direction. `resolve_day` becomes a thin reader of it, and the report reads a whole week of it in one pass.
- A surplus of any excess-sensitive nutrient now lowers the following days, ceilings included, as the spec's ledger rules say.
- `app/reports/summary.py` is pure: what counts as met, which shortfalls were uncompensated and why, and which nutrients and dishes to suggest. `app/reports/service.py` feeds it from the walk, the diary and the plan.
- The suggestions feed the next week's plan, as a stored per-plan emphasis on the planner's nutrient weights.
- Reminders sit behind a channel interface (`app/reminders/channels.py`):
  - web push is the first adapter, through `pywebpush` and VAPID keys from settings;
  - a pure scheduler decides which slots are due;
  - `tick(db, now_utc, channel)` claims each reminder in a delivery table before sending, so reruns never double-send;
  - the loop runs in the FastAPI lifespan only when `SCHEDULER_ENABLED` is set, and a one-shot CLI serves external cron.
- On the frontend, the Report and Reminders screens move onto the real endpoints. The PWA service worker gains push and notification-click handlers through `workbox.importScripts`.
- A household member's weekly progress becomes visible to the household as counts only, never as targets.

**Tech Stack:**
- Backend: FastAPI, SQLAlchemy 2, Alembic and pytest.
- Frontend: React 19, TanStack Query, MSW, Vitest, Recharts, vite-plugin-pwa and Playwright.
- **One new backend dependency:** `pywebpush` (it brings `py-vapid` and `http-ece`). Web push needs VAPID signing and payload encryption, and those are not worth hand-rolling.
- No new frontend dependency.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`. The relevant parts are:
- "2. Compensation ledger": the surplus rule, and "expires → recorded as 'uncompensated' in the weekly report".
- "7. Eating out" (measured vs estimated) and "9. Reminders".
- "Solo Use & Households": weekly progress is shared by default, and health data is never shared.
- The Data Model: `push_subscriptions`.
- Implementation Sequence steps 10–11.
- Testing & Verification: manual steps 5, 9, 12, 13 and 16.
- Safety.

The HTTP contracts are `frontend/src/report/types.ts` and `frontend/src/settings/types.ts`, and both are amended here where the proposal could not express the spec.

**Status:** Complete. 881 backend tests and 334 frontend tests passing, plus 9 Playwright
end-to-end tests against the real backend and Postgres; `ruff`, `alembic check`, `tsc -b`,
`oxlint` and `vite build` clean.

## Global Constraints

**Backend tooling**
- Python `>=3.12` and `ruff` line length 100. Run every backend command as `uv run`, from `backend/`.
- Ruff 0.16 runs its broad default rule set: DTZ (never a naive `datetime.now()` or `date.today()`), I001, RUF022 (sorted `__all__`), UP, B, SIM and PT. E501 is off, but keep lines to 100 columns. Do not add `noqa`.
- Code blocks here are written for reading. Wrap any line over 100 columns before committing.

**Models and migrations**
- Every table extends `TimestampedBase`, and every model is registered in `app/models/__init__.py` with `__all__` kept sorted.
- Tests run against the **migrated** schema. After adding a migration, run all three:
  - `DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test uv run alembic upgrade head`
  - `uv run alembic upgrade head`
  - `uv run alembic check`
- Plan 7's head is `e1f2a3b4c5d6`. Copy the header style of `alembic/versions/e1f2a3b4c5d6_weight_and_cycle.py`; `script.py.mako` generates one that fails ruff.

**Running tests**
- The full backend suite takes about 10 minutes. During a task, run only the test files you touched; the final task runs everything.
- Never run two pytest sessions against the test database at once.

**API conventions**
- Routers commit and services flush. A 422 uses `status.HTTP_422_UNPROCESSABLE_CONTENT`.
- A missing profile answers 404 "Complete your profile first".
- Request and response models live inline in the router as `XxxIn` / `XxxOut`, with both `response_model=` and a return annotation.
- In production, sessions do not autoflush (`sessionmaker(autoflush=False)`), but the test session does. After a write that a later query in the same request reads, `db.flush()` explicitly.

**Dates**
- A user's today is `app.local_time.local_today(user)`.
- Tests that depend on today compute it from `datetime.datetime.now(ZoneInfo("Asia/Kolkata"))`. A fixed date is only for date-parameterised reads.
- Weeks run Sunday to Saturday. `planner.service.week_start_for(day)` gives the Sunday, and `planner.rules.sunday_index(day)` is 0 on Sunday.

**The profile-save trap**
- Never add a table to `profiles.service.CHILD_MODELS`. A profile save deletes every row in those tables.
- `meal_slot_times` is already in that list, which is exactly why `reminder_on` is lost today (Task 9).

**Frontend checks and test conventions**
- Checks: `npx tsc -b` (never `--noEmit` alone), `npx vitest run`, `npm run lint`, `npm run build`.
- Stub endpoints per test with `server.use(...)`. Unhandled requests fail the test.
- Each test file builds its own `QueryClient` with `retry: false`, wrapped in `MemoryRouter` when the screen links anywhere.
- A 404 from a profile-backed endpoint renders the "Set up your profile" `EmptyState`, as Plan, Weight and Cycle do.

**Privacy**
- Health data never leaves its owner. That covers conditions, medications, weight, cycle, and any target figure, since a 1,500 mg sodium cap reveals hypertension and 8 mg of iron reveals menopause.
- The household sees only counts of days on track.

**Copy (Safety section)**
- The report never recommends a medication change.
- Suggestions respect diet type, avoided foods and drug rules. Potassium is never suggested on a potassium-sparing drug, and nothing held steady (vitamin K on an anticoagulant) is ever suggested. The dishes named under a suggestion are filtered by diet and avoided foods only (see Known gaps).
- Nothing presents traditional practice as nutrition.

**Commits**
- Commit after each task, on `tracking-loop-and-ui-foundation`. Do not push.
- Use a conventional prefix and a body that explains the *why*.
- Every message ends with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Decisions taken before starting

Recorded here so the implementer does not re-litigate them; the closeout carries them forward.

**The ledger**
- **One walk, reused.** `walk_ledger(...)` moves the loop out of `resolve_day`.
  - It costs every day against that day's own targets, including the recalibration offset in force (plan 7's per-day costing, now in one place).
  - It records, per day and nutrient: the base and effective targets, what was carried in and from which day (the first, when several days carry onto it), what was consumed, and what expired, with its direction. What each day hands on is recorded per landing day instead (`Ledger.carried`, `Ledger.sources`), summed over the source days and including landings after the walk's end. No reader needs a single source day's outgoing carries, so they are not kept.
  - `resolve_day` keeps its signature and return values. For Today, nothing changes except the surplus rule below.
- **A harmful surplus lowers the next days for every excess-sensitive nutrient, ceilings included.**
  - The spec's ledger rule says an excess-sensitive surplus "reduce[s] the next 2 days' targets", and manual step 5 checks it for sodium.
  - Today a sodium, saturated-fat, free-sugar or cholesterol surplus goes nowhere, because those nutrients do not carry a shortfall, and `_policies` gives them zero carry days in both directions.
  - Surpluses now spread over `SURPLUS_CARRY_DAYS = 2` for any excess-sensitive nutrient that is not held steady, with the same 30% cap per source day.
  - A lowered ceiling has no EAR to stop it, and that is the point.
- **The walk keeps Today's clean slate four days back.** A report's walk starts four days before the Sunday, as Today does. Chains of unmet carries older than that are not followed, so a week's figures can differ slightly from what Today showed on each day. This is recorded as a gap.

**The report**
- **Derived on demand, never stored.** This follows the ledger's precedent: there is nothing to go stale. An old week is re-costed against the current profile and food tables, and that is recorded as a gap. There is no `weekly_reports` table, and no `user_settings` table (plan 9 needs one for LLM keys and creates it then).
- **Which week.**
  - `GET /reports/week?start=` takes a Sunday; any other day is a 422. A week starting after the current one is also a 422.
  - `status` is `complete` once the Saturday has ended in the user's timezone, and `in-progress` for the current week. In an in-progress week, today and later days count in no denominator.
  - The screen opens on the last complete week, with previous and next arrows. Next stops at the current week.
- **A day is "tracked" when anything was logged, and a nutrient is "measured" on a tracked day when something logged carried a figure for it** (coverage > 0). Every total and count is over measured days only, so a gap in the food tables never reads as a deficit.
  - `target_total` is the sum of the day's **base** target (before carries) over measured days. Summing effective targets would count a made-up shortfall twice.
  - `ear_total` sums the EAR over the same days.
- **What counts as met on a measured day.**
  - A target nutrient is met when consumed is at least its EAR (its effective target where there is no EAR) and it stays under its TUL (reaching the TUL is already "above the limit" on Today).
  - A ceiling is met when consumed is under its effective ceiling (reaching it is "above the limit" on Today).
  - This is exactly Today's "on target" band, where "over target" on a target nutrient is not a miss.
  - Days over a TUL are counted separately as `days_over_limit`. Weekly sums are never compared with a daily limit.
- **Uncompensated means shortfalls that expired**, summed per nutrient over the week's source days. Only target nutrients count, and two are left out:
  - **Energy.** Telling someone losing weight that calories were "not made up" works against their goal.
  - **Anything held steady.** Vitamin K on an anticoagulant is not averaged by design.

  Each shortfall carries a `reason_code`:
  - `not_compensable` for protein ("Protein has no storage pool, so a short day is not carried forward.")
  - `cap` otherwise ("Beyond the 30% a day can carry, so it expired.", with that nutrient's own cap)

  Amounts under 1% of the week's target are omitted.
- **Measured versus estimated covers energy only,** matching the contract: entries flagged `is_estimated` against the rest, over tracked days.
- **Meals are accounted per elapsed day.** Expected slots are the currently enabled slots. A slot with an entry is logged. A slot skipped without an entry is skipped, and counts as accounted for. Everything else is missed. Untracked days count as missed.
- **Plan adherence is reported when there is a plan.** It counts planned items on elapsed days, and how many of those slots were logged with the planned dish.
- **Suggestions are structured, not prose.**
  - At most three nutrients are chosen, worst first.
  - Each must be a target nutrient measured on at least half the tracked days (and at least 3), with a mean coverage of at least 0.5, and a week's consumption under 90% of `target_total`.
  - Excluded: energy, anything held steady, and potassium when a potassium-sparing drug is taken (spec manual step 7b).
  - For each nutrient, up to three dishes come from the user's visible, slot-tagged pool that fit the profile's diet and contain no avoided food, ranked by that nutrient per default portion.
  - Shape: `{nutrient_code, display_name, text, foods: [{food_id, name}]}`.
- **Suggestions feed the next plan.**
  - When a week's plan is generated, the nutrients suggested by the report of the week before it get their planner weight multiplied by `EMPHASIS_FACTOR = 1.5`.
  - The emphasis is stored on the plan (`meal_plans.emphasis`), so a swap or a re-plan keeps it, and a regenerate recomputes it.
  - There is no emphasis when the previous week had fewer than 3 tracked days.

**The household**
- **Weekly progress is shared by default, as counts only.** `GET /households/progress?start=` lists the caller and every member with `share_progress`. For each it gives tracked days, and measured nutrient-days met out of measured nutrient-days, over the targets a profile has before the condition overlay, so a condition never changes how many nutrient-days are counted (a target only a condition creates, such as high cholesterol's cholesterol ceiling, would add one per logged day). It never names a nutrient or a target: targets reveal conditions (`share_health` still guards those, and nothing exposes them). Members not sharing progress are listed without figures.

**Reminders**
- **`reminder_on` survives a profile save.**
  - `MealTimeIn.reminder_on` becomes optional. A save that omits it keeps the slot's previous value, and a new slot defaults to on, except the mid-morning snack.
  - The wizard also carries the field through.
  - A one-off data migration turns the mid-morning snack's reminder off where nobody could ever have set it. No UI has ever written `reminder_on`, so no user choice is overridden.
- **Settings.**
  - `GET /settings/reminders` returns the enabled slots in `SLOTS` order, with their times and `reminder_on`, and falls back to `DEFAULT_SLOT_TIMES` for a profile saved before meal times existed. It also returns the number of this user's subscribed devices.
  - `PATCH /settings/reminders {slot, reminder_on}` edits the row in place.
  - `push_granted` leaves the contract: permission is a fact about one browser, which the client reads itself.
- **Web push through VAPID.**
  - Settings carry `vapid_public_key`, `vapid_private_key` and `vapid_subject`. `GET /push/public-key` answers 503 when they are unset, and the screen then says reminders are not set up on this server.
  - `push_subscriptions` is keyed by endpoint. A subscription re-posted by another account moves to that account, so a shared phone reminds only its current user.
  - A 404 or 410 from the push service deletes the subscription.
  - Subscribing also records the browser's timezone on the user when it is a valid zone. Nothing else writes `users.timezone`, and reminder times are wall-clock.
- **When a slot is due.**
  - A slot is due from its time until 60 minutes after it, on the user's local date. The weekend time applies on Saturday and Sunday, as in the planner.
  - It must be enabled and have `reminder_on` set, and it must not already be logged **or skipped**. A skip is an explicit "not eating this", so nagging after it is wrong.
  - A missed tick more than an hour late sends nothing rather than a stale reminder.
- **Exactly once.** Each reminder is claimed with `INSERT … ON CONFLICT DO NOTHING RETURNING` in `reminder_deliveries`, unique on user, local date and slot, before anything is sent. A restart, an overlapping cron run or a second instance cannot double-send.
- **The runner.**
  - An asyncio loop starts in the FastAPI lifespan only when `SCHEDULER_ENABLED=true`, and ticks every 60 s in a worker thread; the backend is sync.
  - The flag defaults to false, because every API test's `TestClient` runs the lifespan against the development database's engine. `tests/conftest.py` forces it off regardless.
  - `uv run python -m scripts.send_reminders` runs one tick, for an external cron.
- **Not built.**
  - Saturday-evening plan generation: a plan generated then misses Saturday's carries (`as_of` excludes the day in progress), and on-demand generation on Sunday is the same plan with them.
  - A scheduled recalibration re-read: without a new weigh-in there is nothing to re-read.
  - Both stay recorded as gaps.
- **Service worker.**
  - It stays `generateSW`, with `workbox.importScripts: ['push-handlers.js']` and a plain-JS `public/push-handlers.js`.
  - `push` always shows what it receives, since a silent push gets a generic notification on Chrome and can revoke the subscription on Safari. The server decides whether to send at all.
  - `notificationclick` navigates to `/log?slot=<slot>`.
- **Subscribing is a button, on a real worker only.**
  - The permission prompt needs a user gesture.
  - The button is shown only when the page is controlled by the production worker (`/sw.js`), because in dev MSW's worker owns the scope and has no push handler.
  - Signing out unsubscribes this device first, since the logout call itself takes no user.


**Rulings on edges the task sections surfaced**

- **A week that has not started where the account keeps time is a calm state, never an error.** The browser's calendar and `users.timezone` can disagree on a Sunday. Both the Report screen (Task 8) and the household progress card (Task 13) treat a 422 for a week that has not begun as "not started yet". The card renders nothing in that case.
- **A stored emphasis never overrides a drug rule.** Task 6's `never_emphasised` drops potassium on a potassium-sparing drug, and anything held steady, from a plan's emphasis on every day. A drug added mid-week therefore takes effect before the next regenerate.
- **`DemoDataBanner` goes.** After Tasks 8 and 12 it has no users. Task 14 deletes it and refreshes the stale mock comments.

---

## File structure

Paths are relative to `backend/` or `frontend/`.

**Backend — create**

| File | Responsibility |
|---|---|
| `app/reports/__init__.py`, `app/reports/summary.py` | Pure report arithmetic: met, uncompensated, suggestions |
| `app/reports/service.py`, `app/reports/router.py` | The week's report from one ledger walk; `GET /reports/week`; household counts |
| `app/models/push.py` | `PushSubscription`, `ReminderDelivery` |
| `alembic/versions/f2a3b4c5d6e7_reports_and_reminders.py` | Two tables, `meal_plans.emphasis`, the composite `meal_logs` index, and the snack1 data step |
| `app/reminders/__init__.py`, `service.py`, `router.py` | Reminder settings and push subscriptions over HTTP |
| `app/reminders/schedule.py` | Pure: which slots are due, and what the reminder says |
| `app/reminders/channels.py` | The `Channel` interface and `WebPushChannel` |
| `app/reminders/runner.py` | `tick`, `run_once`, `run_forever` |
| `scripts/send_reminders.py` | One tick, for an external cron |
| `.env.example` | VAPID and scheduler settings, documented |
| tests | `test_ledger_walk.py`, `test_push_models.py`, `test_report_summary.py`, `test_reports_api.py`, `test_household_progress_api.py`, `test_reminders_api.py`, `test_reminder_schedule.py`, `test_reminder_runner.py`, `test_webpush_channel.py` |

**Backend — modify**

| File | Change |
|---|---|
| `app/nutrition_core/compensation.py` | `SURPLUS_CARRY_DAYS`, `NutrientPolicy.surplus_days` |
| `app/targets/service.py` | `_policies` surplus days; `TargetContext`, `load_context`, `base_targets_on`, `LedgerDay`, `Ledger`, `walk_ledger`; `resolve_day` reads the walk |
| `app/diary/service.py`, `app/diary/router.py` | `day_breakdown`, `slot_states`; `read_diary` uses `slot_states` |
| `app/planner/engine.py`, `app/planner/service.py` | `NutrientGoal.weight`, `EMPHASIS_FACTOR`; the plan's emphasis is computed, stored and applied |
| `app/households/router.py` | `GET /households/progress` |
| `app/profiles/router.py`, `app/profiles/service.py` | `reminder_on` survives a save; snack1 defaults off |
| `app/models/plan.py`, `app/models/diary.py`, `app/models/__init__.py` | `emphasis`; the composite index; registration |
| `app/config.py` | VAPID keys, `scheduler_enabled` |
| `app/local_time.py` | `local_now(user, now_utc)` |
| `app/main.py` | Three routers; the lifespan |
| `pyproject.toml`, `uv.lock` | `pywebpush` |
| `scripts/e2e_session.py` | `OWNED_MODELS` gains the two new tables |
| `tests/conftest.py` | The scheduler forced off |

**Frontend — modify (and create where marked)**

| File | Change |
|---|---|
| `src/report/types.ts`, `ReportScreen.tsx`, `EnergyChart.tsx`, `ReportScreen.test.tsx`; `useReport.ts` (create) | The Report screen on the real endpoint, with week navigation |
| `src/settings/types.ts`, `RemindersScreen.tsx`, `RemindersScreen.test.tsx`; `useReminders.ts`, `usePush.ts` and tests (create) | Reminder settings, and push on this device |
| `public/push-handlers.js` (create), `vite.config.ts` | Service-worker push and notification-click handlers |
| `src/auth/useSession.ts` | Sign-out unsubscribes this device first |
| `src/onboarding/types.ts`, `validation.ts`, `useProfile.ts`, `OnboardingWizard.tsx` | `reminder_on` carried through the wizard |
| `src/households/HouseholdScreen.tsx`, `useHousehold.ts` | The week's progress card |
| `src/ui/NutrientBar.tsx` | "Lowered by … after {day}" for a negative carry |
| `src/mocks/handlers/index.ts`, `src/mocks/fixtures/*` | The last fixture handlers go |
| `src/ui/feedback.tsx` | `DemoDataBanner` removed |
| `e2e/smoke.spec.ts` | Report and reminders walks |
| `README.md` | Every screen is real |

**Docs — modify:** `docs/superpowers/plans/README.md`, this plan's Status line, the UI-foundation contract table, and one overclaim in plan 7.

---

## Task 1: A harmful surplus lowers the next days, ceilings included

Right now a sodium, saturated-fat, free-sugar or cholesterol surplus lowers nothing. `_spread` uses the nutrient's compensation days in both directions. Those four never carry a shortfall, because a low-salt day is not a debt, so `_policies` gives them zero days and their surplus expires on the spot. The spec's ledger rule lowers "the next 2 days' targets" after any excess-sensitive surplus, and manual step 5 checks it for sodium.

This task gives a surplus its own days, `surplus_days`:
- The ceilings get `SURPLUS_CARRY_DAYS = 2`, with the same 30% cap per source day.
- A compensable nutrient keeps its own compensation days, so energy, calcium and iron behave exactly as before.
- A nutrient held steady gets none.

A lowered ceiling has no EAR to stop it, and that is the point: less sodium is never a shortfall. It is still bounded. At most two source days land on any day, so two very salty days in a row take the ceiling to about 40% of its base, and no lower. Today shows the lowered figure as `target_effective`, and the planner plans the next two days against it.

**Files:**
- Modify: `app/nutrition_core/compensation.py`, `app/targets/service.py` (`_policies`)
- Test: `tests/test_compensation.py` (append), `tests/test_tracking_api.py` (append one API test and the sodium-bearing dish fixture it uses)

**Interfaces:**
- Consumes: the `nutrients` policy columns (`is_compensable`, `compensation_days`, `is_excess_sensitive`) and the overlay's `compensation_disabled`, which `_policies` already reads.
- Produces:
```python
# app/nutrition_core/compensation.py
SURPLUS_CARRY_DAYS = 2

@dataclass(frozen=True)
class NutrientPolicy:
    code: str
    is_compensable: bool
    compensation_days: int
    is_excess_sensitive: bool
    ear: float | None
    tul: float | None
    carry_cap_fraction: float = DEFAULT_CARRY_CAP
    # Days a harmful surplus is spread over. None means compensation_days, which is
    # every existing call site's behaviour.
    surplus_days: int | None = None

def _spread(policy, amount, base_target, sign: int, days: int) -> CarryPlan
    # the shortfall path passes compensation_days; the surplus path passes
    # surplus_days if not None else compensation_days

# app/targets/service.py -- _policies sets surplus_days on every policy:
#   row.compensation_days when compensable; else SURPLUS_CARRY_DAYS when
#   excess-sensitive and not in `disabled`; else 0.
```

- [ ] **Step 1: Write the failing tests**

In `tests/test_compensation.py`, replace the import block. It runs from `import pytest` down to the closing parenthesis of the `app.nutrition_core.compensation` import. The replacement is:

```python
import pytest

from app.models.nutrient import Nutrient
from app.nutrition_core.compensation import (
    DEFAULT_CARRY_CAP,
    SURPLUS_CARRY_DAYS,
    NutrientPolicy,
    effective_target,
    plan_carry,
)
from app.nutrition_core.targets import Target
from app.targets.service import _policies
```

Append to the end of `tests/test_compensation.py`:

```python


# --- a harmful surplus of a ceiling -------------------------------------------
#
# Sodium carries no shortfall, so its policy has no compensation days -- and until
# a surplus had days of its own, a 4,000 mg day lowered nothing at all. The spec
# lowers the next two days after any excess-sensitive surplus (manual step 5).

# Sodium as `_policies` builds it: no shortfall carry, no EAR, and no ICMR upper
# limit -- its 2,000 mg figure is itself the ceiling.
SALT = policy(
    code="sodium", is_compensable=False, compensation_days=0,
    is_excess_sensitive=True, ear=None, tul=None, surplus_days=SURPLUS_CARRY_DAYS,
)


def test_a_salty_day_lowers_the_next_two_days():
    """A 2,000 mg surplus halves to 1,000 mg a day, past the 30% cap of 600 mg."""
    plan = plan_carry(SALT, consumed=4000, effective_target=2000, base_target=2000)

    assert [carry.day_offset for carry in plan.carries] == [1, 2]
    assert [carry.amount for carry in plan.carries] == [-600, -600]


def test_what_the_cap_refuses_of_a_salty_day_expires():
    plan = plan_carry(SALT, consumed=4000, effective_target=2000, base_target=2000)

    assert plan.expired == pytest.approx(800)


def test_a_modest_sodium_surplus_is_split_evenly():
    plan = plan_carry(SALT, consumed=2600, effective_target=2000, base_target=2000)

    assert [carry.amount for carry in plan.carries] == [-300, -300]
    assert plan.expired == 0


def test_a_sodium_shortfall_still_never_carries_up():
    """Surplus days are for a surplus. A low-salt day is not a debt."""
    plan = plan_carry(SALT, consumed=900, effective_target=2000, base_target=2000)

    assert plan.carries == ()


def test_a_lowered_ceiling_has_no_floor_to_stop_it():
    """Two salty days in a row add up, and nothing props the ceiling back up:
    less sodium is never a shortfall."""
    assert effective_target(SALT, base_target=2000, carried_in=-600) == 1400
    assert effective_target(SALT, base_target=2000, carried_in=-1200) == 800


def test_surplus_days_default_to_the_compensation_days():
    """Unset, a surplus spreads exactly as it did before surplus days existed."""
    plan = plan_carry(
        policy(compensation_days=1), consumed=1400, effective_target=1000, base_target=1000
    )

    assert [carry.day_offset for carry in plan.carries] == [1]
    assert [carry.amount for carry in plan.carries] == [-300]


def test_surplus_days_leave_a_shortfall_to_the_compensation_days():
    plan = plan_carry(
        policy(compensation_days=1, surplus_days=2),
        consumed=600, effective_target=1000, base_target=1000,
    )

    assert [carry.day_offset for carry in plan.carries] == [1]


def test_no_surplus_days_lets_the_whole_surplus_expire():
    """What a nutrient held steady gets: it is smoothed in neither direction."""
    plan = plan_carry(
        policy(surplus_days=0), consumed=1400, effective_target=1000, base_target=1000
    )

    assert plan.carries == ()
    assert plan.expired == pytest.approx(400)


# --- how the targets service builds each policy ---------------------------------


def nutrient_row(code: str, compensable: bool, days: int, excess_sensitive: bool) -> Nutrient:
    """A `nutrients` row, never saved: `_policies` reads only its policy columns."""
    return Nutrient(
        code=code, display_name=code, unit="mg", category="mineral",
        is_compensable=compensable, compensation_days=days,
        is_excess_sensitive=excess_sensitive,
    )


# The policy columns as the seed has them (etl/load_nutrients.py).
ROWS = {
    "sodium": nutrient_row("sodium", compensable=False, days=0, excess_sensitive=True),
    "calcium": nutrient_row("calcium", compensable=True, days=2, excess_sensitive=True),
    "vitamin_k": nutrient_row("vitamin_k", compensable=True, days=1, excess_sensitive=False),
    "protein": nutrient_row("protein", compensable=False, days=0, excess_sensitive=False),
}
TARGETS = {
    "sodium": Target("sodium", ear=None, rda=2000.0, tul=None, kind="ceiling"),
    "calcium": Target("calcium", ear=800.0, rda=1000.0, tul=2500.0, kind="target"),
    "vitamin_k": Target("vitamin_k", ear=None, rda=55.0, tul=None, kind="target"),
    "protein": Target("protein", ear=42.9, rda=53.95, tul=None, kind="target"),
}


def test_a_ceiling_spreads_a_surplus_over_two_days_and_carries_no_shortfall():
    sodium = _policies(TARGETS, ROWS, disabled=frozenset())["sodium"]

    assert sodium.surplus_days == SURPLUS_CARRY_DAYS
    assert sodium.is_compensable is False
    assert sodium.compensation_days == 0


def test_a_compensable_nutrient_spreads_a_surplus_as_it_always_has():
    policies = _policies(TARGETS, ROWS, disabled=frozenset())

    assert policies["calcium"].surplus_days == 2
    assert policies["vitamin_k"].surplus_days == 1


def test_a_nutrient_that_is_not_excess_sensitive_has_no_surplus_days():
    assert _policies(TARGETS, ROWS, disabled=frozenset())["protein"].surplus_days == 0


def test_a_nutrient_held_steady_is_not_lowered_after_a_surplus():
    """Only vitamin K is held steady today, on warfarin. Whatever is held steady
    next -- a ceiling included -- is smoothed in neither direction."""
    policies = _policies(TARGETS, ROWS, disabled=frozenset({"vitamin_k", "sodium"}))

    assert policies["vitamin_k"].surplus_days == 0
    assert policies["sodium"].surplus_days == 0
```

In `tests/test_tracking_api.py`, replace the two imports at the top (`import datetime`, a blank line, then `import pytest`) with:

```python
import datetime

import pytest
from sqlalchemy import select

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
```

Append to the end of `tests/test_tracking_api.py`:

```python


# --- a harmful surplus lowers the next days, ceilings included ---------------
#
# Spec manual step 5: log a very high-sodium day, and the next days' sodium
# ceilings drop. Sodium carries no shortfall -- a low-salt day is not a debt --
# and until a surplus had days of its own to spread over, a salty day went nowhere.


@pytest.fixture
def salty_dish(db, reference_data) -> Dish:
    """1,000 mg of sodium per 100 g and nothing else, so no other nutrient moves."""
    sodium = db.scalar(select(Nutrient).where(Nutrient.code == "sodium"))
    ingredient = Ingredient(code="test:salted-mixture", name="Salted mixture", source="IFCT")
    db.add(ingredient)
    db.flush()
    db.add(
        IngredientNutrient(
            ingredient_id=ingredient.id, nutrient_id=sodium.id, per_100g=1000.0, source="IFCT"
        )
    )
    dish = Dish(
        code="test:mixture-plate",
        name="Mixture plate",
        source="authored",
        is_editable=True,
        yield_factor=1.0,
    )
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ingredient.id, grams=100.0))
    db.flush()
    return dish


def test_a_salty_day_lowers_the_next_two_days_sodium_ceilings(signed_in, salty_dish):
    """4,000 mg against the 2,000 mg ceiling is a 2,000 mg surplus. Half of it is
    1,000 mg a day, past the 30% cap, so each of the next two days is lowered by
    600 mg, to 1,400 mg -- and the day after those is back to 2,000 mg."""
    signed_in.put("/profile", json=PROFILE)
    logged = signed_in.post(
        "/diary/entries",
        json={
            "date": str(YESTERDAY), "slot": "lunch", "food_id": str(salty_dish.id),
            "food_kind": "dish", "grams": 400, "is_estimated": False,
        },
    )
    assert logged.status_code == 201, logged.text

    for offset in (0, 1):
        day = TODAY + datetime.timedelta(days=offset)
        sodium = nutrient(signed_in.get(f"/targets/today?date={day}").json(), "sodium")
        assert sodium["rda"] == 2000
        assert sodium["carried_in"] == pytest.approx(-600)
        assert sodium["target_effective"] == pytest.approx(1400)
        assert sodium["carried_from"] == "Sunday"  # 16 August 2026

    after = TODAY + datetime.timedelta(days=2)
    sodium = nutrient(signed_in.get(f"/targets/today?date={after}").json(), "sodium")
    assert sodium["carried_in"] == 0
    assert sodium["target_effective"] == pytest.approx(2000)
```

The API test uses the file's fixed `TODAY` (17 August 2026). This is safe:
- `/targets/today?date=` is a date-parameterised read with no `as_of`, so every day before the one asked about counts as ended.
- The profile save's weigh-in is dated the real today, so no recalibration offset reaches August.
- The dish carries sodium alone. The day's totals are `{"sodium": 4000.0}`, so no other nutrient's ledger moves.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_compensation.py tests/test_tracking_api.py -q --continue-on-collection-errors`

Expected:
- `tests/test_compensation.py` errors at collection with `ImportError: cannot import name 'SURPLUS_CARRY_DAYS' from 'app.nutrition_core.compensation'`.
- `test_a_salty_day_lowers_the_next_two_days_sodium_ceilings` FAILS with `assert 0.0 == -600 ± 6.0e-04`, because today the salty day lowers nothing.
- The rest of `test_tracking_api.py` passes.

- [ ] **Step 3: Give a surplus its own days**

In `app/nutrition_core/compensation.py`:

1. Below `CARRY_CAPS = {"fibre": FIBRE_CARRY_CAP}`, add:

```python

# How many following days a harmful surplus is taken back out of, when the
# nutrient carries no shortfall. The spec lowers "the next 2 days' targets" after
# any excess-sensitive surplus. Sodium and the other ceilings are never carried
# up, since a low-salt day is not a debt, but a salty day still lowers the next two.
SURPLUS_CARRY_DAYS = 2
```

2. In `NutrientPolicy`, add after `carry_cap_fraction: float = DEFAULT_CARRY_CAP`:

```python
    # Days a harmful surplus is spread over. None means compensation_days, which is
    # every existing call site's behaviour.
    surplus_days: int | None = None
```

3. Replace the whole `_spread` function with this version. It takes its day count from the caller, and the one over-long line is wrapped.

```python
def _spread(
    policy: NutrientPolicy, amount: float, base_target: float, sign: int, days: int
) -> CarryPlan:
    if days <= 0:
        return CarryPlan(carries=(), expired=amount)

    per_day_cap = base_target * policy.carry_cap_fraction
    share = amount / days

    carried = min(share, per_day_cap)
    carries = tuple(
        Carry(day_offset=offset, amount=sign * carried) for offset in range(1, days + 1)
    )

    # Anything the cap refused is gone: the debt does not roll onward for ever.
    return CarryPlan(carries=carries, expired=amount - carried * days)
```

4. Replace the whole `_plan_shortfall` function with this version. It passes its day count, and its docstring no longer says every expired shortfall is reported: a ceiling's never is.

```python
def _plan_shortfall(policy: NutrientPolicy, deficit: float, base_target: float) -> CarryPlan:
    """A deficit only carries when the body can actually buffer the nutrient.

    Protein cannot (no storage pool), and a sodium shortfall is not a deficit
    worth making up at all — both fall through to `expired`. Only a target
    nutrient's expired shortfall is reported as uncompensated (protein's, for
    instance); a ceiling's never is, since less sodium is not a gap.
    """
    if not policy.is_compensable:
        return CarryPlan(carries=(), expired=deficit)
    return _spread(policy, deficit, base_target, sign=1, days=policy.compensation_days)
```

5. Replace the whole `_plan_surplus` function with:

```python
def _plan_surplus(policy: NutrientPolicy, surplus: float, base_target: float) -> CarryPlan:
    """Only a storable, harmful surplus is worth rebalancing downward.

    Water-soluble vitamin surpluses are excreted, so there is nothing to
    rebalance and nothing to report — those return an empty plan with no expiry,
    which is different from a shortfall that expired.

    A harmful one spreads over `surplus_days` rather than `compensation_days`:
    sodium carries no shortfall, but a salty day still lowers the days after it.
    """
    if not policy.is_excess_sensitive:
        return CarryPlan(carries=(), expired=0.0)
    days = policy.surplus_days if policy.surplus_days is not None else policy.compensation_days
    return _spread(policy, surplus, base_target, sign=-1, days=days)
```

- [ ] **Step 4: Set the surplus days in `_policies`**

In `app/targets/service.py`:

1. Add `SURPLUS_CARRY_DAYS,` as the first name in the `from app.nutrition_core.compensation import (...)` block. Ruff's isort puts constants before classes, so it goes above `NutrientPolicy`.

2. Replace the whole `_policies` function with:

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
```

`resolve_day` itself does not change. Its walk already hands every carry that `plan_carry` returns to the following days.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_compensation.py tests/test_tracking_api.py tests/test_targets_service.py tests/test_weight_service.py tests/test_weight_api.py tests/test_menstrual_status.py tests/test_planner_api.py -q && uv run ruff check .`

Expected: all PASS, and ruff is clean. The other suites read the ledger and pass unchanged, for three reasons:
- None of their foods carries sodium, saturated fat, free sugar or cholesterol. Those foods are the fixture rice (energy, protein and calcium), the planner pool (which adds potassium, B12 and fibre) and the iron dish.
- Every compensable nutrient's surplus days equal its compensation days.
- The existing `SODIUM` policy in `test_compensation.py` leaves `surplus_days` unset, so `test_a_sodium_shortfall_never_carries_up` still exercises the default path.

- [ ] **Step 6: Commit**

```bash
git add app/nutrition_core/compensation.py app/targets/service.py \
  tests/test_compensation.py tests/test_tracking_api.py
git commit -m "fix(backend): let a harmful surplus lower the next days, ceilings included

The spec lowers the next two days' targets after any excess-sensitive
surplus, and manual step 5 checks it for sodium. But a surplus was spread
over the nutrient's compensation days, and sodium, saturated fat, free
sugar and cholesterol have none: they never carry a shortfall, since a
low-salt day is not a debt. So a 4,000 mg sodium day lowered nothing.

A surplus now has days of its own. The ceilings spread theirs over two,
under the same 30% cap per source day, so that day takes each of the next
two ceilings to 1,400 mg. A compensable nutrient keeps its own days, and one
held steady gets none. A lowered ceiling has no EAR to stop it, which is the
point: less sodium is never a shortfall. Today and the planner both read
the lowered figure.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: One ledger walk, reused

The weekly report needs a week of the ledger: which days were tracked, what each day was carried, and what expired, in which direction. `resolve_day` already works all of that out, inside a loop, and then throws it away. This task moves that loop into `walk_ledger`, which records every source day as it goes, and makes `resolve_day` one reader of it. Plan 7's per-day offset costing moves with it into `base_targets_on`, so every reader costs a day at the recalibration in force on that day. The task adds no behaviour: `resolve_day` returns the same figures to the last decimal. Task 1's surplus rule, which lands first, reaches the walk through the policies unchanged.

**Files:**
- Modify: `app/targets/service.py` (the walk leaves `resolve_day`, which becomes a reader of it)
- Test:
  - `tests/test_ledger_walk.py` (create)
  - `tests/test_tracking_api.py`, `tests/test_targets_service.py`, `tests/test_weight_service.py` and `tests/test_planner_api.py` must pass unchanged

**Interfaces:**
- Consumes:
  - Task 1: `NutrientPolicy.surplus_days`, and `_policies` as Task 1 left it. The walk hands each policy to `plan_carry` untouched.
  - Plan 7: `weight.offset_on`, `profiles.body_of`, `recalibration.lowest_target` and `_ENERGY_DERIVED_CODES`.
- Produces (all in `app/targets/service.py`):
```python
@dataclass(frozen=True)
class TargetContext:
    profile: Profile
    body: Body
    formula: float                       # energy_target(body, goal, pace)
    references: dict[str, ReferenceValue]
    upper_limits: dict[str, float]
    overlay: OverlayResult               # the context date's targets, warnings, disabled
    nutrients: dict[str, Nutrient]
    policies: dict[str, NutrientPolicy]  # floors={"energy": lowest_target(body, formula)}
    energy_offset_kcal: float            # the offset in force on the context date
    built: dict[str, Target]             # build_targets at that offset, before the overlay

def load_context(db, user, on_date) -> TargetContext | None    # None: no profile
def base_targets_on(db, user, ctx, day) -> dict[str, float]    # code -> base (rda) on day

@dataclass(frozen=True)
class LedgerDay:
    date: datetime.date
    tracked: bool                        # something logged, and day < as_of
    consumed: dict[str, float]           # {} when untracked
    base: dict[str, float]               # base_targets_on(day)
    effective: dict[str, float]          # every code
    carried_in: dict[str, float]
    carried_from: dict[str, datetime.date]
    expired_shortfall: dict[str, float]  # >= 0; a code only when the day fell short of it
    expired_surplus: dict[str, float]    # >= 0; a code only when the day went over it

@dataclass(frozen=True)
class Ledger:
    days: dict[datetime.date, LedgerDay]                    # every day start..end
    carried: dict[datetime.date, dict[str, float]]          # sparse; landings after end too
    sources: dict[datetime.date, dict[str, datetime.date]]  # sparse, likewise

def walk_ledger(db, user, ctx, start, end, as_of=None) -> Ledger
def resolve_day(db, user, target_date, as_of=None) -> DayTargets | None  # unchanged
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ledger_walk.py`:

```python
"""The compensation ledger's walk: one pass that Today and the weekly report share.

The fixture dish is 150 kcal, 4 g protein and 30 mg calcium per 100 g, and
carries nothing else. The profile is the reference man: calcium 1,000 mg (EAR
800), protein 0.83 g per kg of his 65 kg, energy from the formula. Each carry
day may take at most 30% of a target, for two days.

Dates run relative to the real today, because a profile save records a weigh-in
dated today, and a recalibration step can only be taken from today.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.user import User
from app.nutrition_core.energy import Body, energy_target
from app.targets import service as targets
from app.weight import service as weight
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


# The day most tests log on: both of its carry days land before today.
SOURCE = days_ago(3)


def after(day: datetime.date, n: int) -> datetime.date:
    return day + datetime.timedelta(days=n)


def formula(weight_kg: float) -> float:
    body = Body(sex="male", age=25, weight_kg=weight_kg, activity="sedentary")
    return energy_target(body, goal="maintain", pace=None)


def signed_in_user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return signed_in_user(db)


def log_rice(api, dish, on_date: datetime.date, grams: float) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(on_date), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": grams, "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


def walk(db, user, start: datetime.date, end: datetime.date, as_of=None):
    context = targets.load_context(db, user, TODAY)
    return targets.walk_ledger(db, user, context, start, end, as_of)


def take_a_step(db, user) -> None:
    """Three weeks of steady gain on a maintain goal: a -210 kcal step, from today.

    Four weigh-ins, because a step needs two consecutive readings to agree: 0.5
    kg/week as of today, and as of last week's weigh-in.
    """
    weight.record_weigh_in(db, user, days_ago(21), 64.5)
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    weight.record_weigh_in(db, user, days_ago(7), 65.5)
    step = weight.record_weigh_in(db, user, TODAY, 66.0)
    # Checked for None first, so a missing step fails here as an assertion, not
    # later as an AttributeError that looks like the expected load_context failure.
    assert step is not None and step.offset_kcal == -210.0


def row(resolved, code: str):
    return next(n for n in resolved.nutrients if n.code == code)


# --- the context ---------------------------------------------------------------


def test_there_is_no_context_without_a_profile(signed_in, db):
    assert targets.load_context(db, signed_in_user(db), TODAY) is None


# --- which days are tracked ----------------------------------------------------


def test_the_walk_records_every_day_from_start_to_end(db, user):
    ledger = walk(db, user, SOURCE, after(SOURCE, 2))
    assert sorted(ledger.days) == [SOURCE, after(SOURCE, 1), after(SOURCE, 2)]


def test_a_day_with_nothing_logged_is_untracked(db, user):
    day = walk(db, user, SOURCE, SOURCE).days[SOURCE]

    assert day.tracked is False
    assert day.consumed == {}
    assert day.expired_shortfall == {}
    # It still has targets: the report draws them.
    assert day.base["calcium"] == 1000
    assert day.effective["calcium"] == 1000


@pytest.mark.parametrize("as_of_lead", [0, 1])
def test_a_day_on_or_after_as_of_is_untracked(db, user, signed_in, reference_data, as_of_lead):
    """A day still being eaten is part of a day: it neither carries nor expires."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE, as_of=SOURCE - datetime.timedelta(days=as_of_lead))
    day = ledger.days[SOURCE]

    assert day.tracked is False
    assert day.consumed == {}
    assert day.expired_shortfall == {}
    assert ledger.carried == {}


def test_a_day_before_as_of_has_ended(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, SOURCE, SOURCE, as_of=after(SOURCE, 1)).days[SOURCE]

    assert day.tracked is True
    assert day.consumed["calcium"] == pytest.approx(15.0)


# --- what expires --------------------------------------------------------------


def test_a_protein_shortfall_expires_whole(db, user, signed_in, reference_data):
    """Protein has no storage pool: nothing is carried, so the whole shortfall expires."""
    log_rice(signed_in, reference_data, SOURCE, 50)  # 2 g of protein

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_shortfall["protein"] == pytest.approx(65 * 0.83 - 2.0)
    assert all("protein" not in amounts for amounts in ledger.carried.values())


def test_a_shortfall_beyond_the_cap_expires(db, user, signed_in, reference_data):
    # 15 mg of calcium is 985 mg short. Two days at 30% of 1,000 mg carry 600 mg;
    # the other 385 mg is never made up.
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, SOURCE, SOURCE).days[SOURCE]

    assert day.expired_shortfall["calcium"] == pytest.approx(385.0)
    # Energy caps the same way, at 30% of its own target: 75 kcal eaten, 60% carried.
    assert day.expired_shortfall["energy"] == pytest.approx(0.4 * formula(65.0) - 75.0)


def test_a_shortfall_inside_the_cap_is_carried_whole(db, user, signed_in, reference_data):
    # 900 mg of calcium is 100 mg short: 50 mg a day, well inside the cap.
    log_rice(signed_in, reference_data, SOURCE, 3000)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_shortfall["calcium"] == pytest.approx(0.0, abs=1e-9)
    assert ledger.carried[after(SOURCE, 1)]["calcium"] == pytest.approx(50.0)


def test_a_harmful_surplus_beyond_the_cap_expires(db, user, signed_in, reference_data):
    # 4,500 kcal. Each of the next two days is lowered by 30% of the target; the
    # rest of the surplus is recorded as expired, in its own direction.
    log_rice(signed_in, reference_data, SOURCE, 3000)
    target = formula(65.0)

    ledger = walk(db, user, SOURCE, SOURCE)
    day = ledger.days[SOURCE]

    assert day.expired_surplus["energy"] == pytest.approx(4500.0 - 1.6 * target)
    assert "energy" not in day.expired_shortfall
    assert ledger.carried[after(SOURCE, 1)]["energy"] == pytest.approx(-0.3 * target)


def test_an_excreted_surplus_neither_carries_nor_expires(db, user, signed_in, reference_data):
    # 120 g of protein is over the target, but the body has nothing to rebalance.
    log_rice(signed_in, reference_data, SOURCE, 3000)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_surplus.get("protein", 0.0) == 0.0
    assert "protein" not in ledger.carried[after(SOURCE, 1)]


def test_an_unmeasured_nutrient_neither_carries_nor_expires(db, user, signed_in, reference_data):
    """The fixture dish has no potassium row: its zero is silence, not a shortfall."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE)
    day = ledger.days[SOURCE]

    assert "potassium" not in day.consumed
    assert "potassium" not in day.expired_shortfall
    assert all("potassium" not in amounts for amounts in ledger.carried.values())
    assert day.effective["potassium"] == 3510


# --- what is carried -----------------------------------------------------------


def test_carries_landing_after_the_walk_are_kept(db, user, signed_in, reference_data):
    """The day after a walk is the day Today asks about, so its carries must survive."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.carried[after(SOURCE, 1)]["calcium"] == pytest.approx(300.0)
    assert ledger.carried[after(SOURCE, 2)]["calcium"] == pytest.approx(300.0)
    assert ledger.sources[after(SOURCE, 1)]["calcium"] == SOURCE
    assert ledger.sources[after(SOURCE, 2)]["calcium"] == SOURCE


def test_a_carry_raises_the_next_walked_days_target(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    next_day = walk(db, user, SOURCE, after(SOURCE, 1)).days[after(SOURCE, 1)]

    assert next_day.carried_in["calcium"] == pytest.approx(300.0)
    assert next_day.carried_from["calcium"] == SOURCE
    assert next_day.base["calcium"] == 1000
    assert next_day.effective["calcium"] == pytest.approx(1300.0)
    assert "protein" not in next_day.carried_in
    # Nothing was logged on it, so what it was handed simply lapses.
    assert next_day.tracked is False
    assert next_day.expired_shortfall == {}


def test_the_walk_starts_from_a_clean_slate(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, after(SOURCE, 1), after(SOURCE, 1)).days[after(SOURCE, 1)]

    assert day.carried_in == {}
    assert day.effective["calcium"] == 1000


# --- resolve_day reads the walk ------------------------------------------------


def test_resolve_day_reads_its_carries_from_the_walk(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    calcium = row(targets.resolve_day(db, user, after(SOURCE, 1)), "calcium")

    assert calcium.carried_in == pytest.approx(300.0)
    assert calcium.target_effective == pytest.approx(1300.0)
    assert calcium.carried_from == SOURCE.strftime("%A")


def test_resolve_day_hands_as_of_to_the_walk(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    calcium = row(targets.resolve_day(db, user, after(SOURCE, 1), as_of=SOURCE), "calcium")

    assert calcium.carried_in == 0
    assert calcium.target_effective == pytest.approx(1000.0)


# --- each day at its own recalibration offset ----------------------------------


def test_base_targets_follow_the_offset_in_force_on_each_day(db, user):
    take_a_step(db, user)
    context = targets.load_context(db, user, TODAY)
    stepped = formula(66.0) - 210.0

    today = targets.base_targets_on(db, user, context, TODAY)
    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    assert today["energy"] == pytest.approx(stepped)
    assert yesterday["energy"] == pytest.approx(formula(66.0))
    # Thiamine is energy-scaled (1.4 mg sedentary), so the step moves it too.
    assert today["thiamine"] == pytest.approx(1.4 * stepped / formula(66.0))
    assert yesterday["thiamine"] == pytest.approx(1.4)
    # Protein is per kilogram of the body, and no offset moves it.
    assert today["protein"] == pytest.approx(66.0 * 0.83)
    assert yesterday["protein"] == pytest.approx(66.0 * 0.83)


def test_the_context_date_does_not_set_another_days_offset(db, user):
    take_a_step(db, user)
    context = targets.load_context(db, user, days_ago(1))

    today = targets.base_targets_on(db, user, context, TODAY)
    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    assert today["energy"] == pytest.approx(formula(66.0) - 210.0)
    assert yesterday["energy"] == pytest.approx(formula(66.0))


def test_a_target_a_condition_set_keeps_the_context_dates_figure(signed_in, reference_data, db):
    profile = {**PROFILE, "conditions": ["high_cholesterol"]}
    assert signed_in.put("/profile", json=profile).status_code == 200
    user = signed_in_user(db)
    take_a_step(db, user)
    context = targets.load_context(db, user, TODAY)

    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    # High cholesterol sets saturated fat at 7% of the context date's energy. The
    # offset is not all that moved it, so it is not rebuilt at yesterday's.
    assert yesterday["saturated_fat"] == pytest.approx((formula(66.0) - 210.0) * 0.07 / 9)
    # Total fat, which no condition touches, follows yesterday's own energy.
    assert yesterday["fat"] == pytest.approx(formula(66.0) * 0.25 / 9)


def test_the_walk_costs_each_day_at_its_own_offset(db, user, signed_in, reference_data):
    """Yesterday was eaten exactly at its own, pre-step, target. Today's step must
    not turn that into a surplus."""
    take_a_step(db, user)
    log_rice(signed_in, reference_data, days_ago(1), formula(66.0) / 150.0 * 100.0)

    ledger = walk(db, user, days_ago(1), TODAY)
    yesterday = ledger.days[days_ago(1)]
    today = ledger.days[TODAY]

    assert yesterday.base["energy"] == pytest.approx(formula(66.0))
    assert yesterday.expired_surplus.get("energy", 0.0) == pytest.approx(0.0, abs=1e-6)
    assert today.base["energy"] == pytest.approx(formula(66.0) - 210.0)
    assert today.carried_in.get("energy", 0.0) == pytest.approx(0.0, abs=1e-6)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_ledger_walk.py -q`
Expected: FAIL, with 19 failed and 2 passed. Every failure is `AttributeError: module 'app.targets.service' has no attribute 'load_context'`. The two `resolve_day` tests pass already, because they pin what the refactor must keep.

- [ ] **Step 3: Load the context once, and cost any day against it**

In `app/targets/service.py`:

1. Replace the module docstring with:

```python
"""Resolve a user's targets for one day, and walk the compensation ledger.

This is where the pure `nutrition_core` functions meet the database: reference
rows in, a day's targets out, with the compensation ledger recomputed from the
diary rather than stored as a running total. `walk_ledger` is that
recomputation. Today reads one day of it through `resolve_day`; the weekly
report reads a whole week of it in one pass.
"""
```

2. Replace these two imports:

```python
from app.nutrition_core.conditions import Warning, apply_conditions
from app.nutrition_core.energy import energy_target
```

with:

```python
from app.nutrition_core.conditions import OverlayResult, Warning, apply_conditions
from app.nutrition_core.energy import Body, energy_target
```

Leave the `app.nutrition_core.compensation` import as Task 1 left it. Keep `defaultdict`, because the walk uses it.

3. In the comment above `_ENERGY_DERIVED_CODES`, replace its last two lines:

```python
# window day whose offset differs from target_date's must be costed against
# its own figure for these -- never against target_date's stepped one.
```

with:

```python
# day whose offset differs from the context date's must be costed against its
# own figure for these -- never against the context date's stepped one.
```

4. Add below `DayTargets`:

```python
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
```

5. Add below `_iron_limit_warnings`, above `resolve_day`:

```python
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
```

How these carry over plan 7's rule:
- `load_context` runs the queries `resolve_day` ran, in the same order.
- `base_targets_on` applies plan 7's rule unchanged. `apply_conditions` copies the dict, so a target the overlay left alone is the same object in `built`, while `_retarget` always makes a new one. The identity test therefore tells "moved only by the offset" from "set by a condition".
- `_built_at` replaces the old `_targets_for_offset` closure. It has no memo: `build_targets` is arithmetic, and it runs only for a day whose offset differs from the context date's.

- [ ] **Step 4: The walk**

1. Add below `TargetContext`:

```python
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
```

2. Add below `base_targets_on`:

```python
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
```

This is `resolve_day`'s loop, statement for statement:
- The days and codes come in the same order.
- It makes the same `effective_target` and `plan_carry` calls on the same figures.
- `setdefault` keeps the first source day.
- A day on or after `as_of` is never read from the diary.

Two things are new. The loop records each day, and it looks up every day's offset, including untracked days, because `LedgerDay.base` is for every day.

- [ ] **Step 5: `resolve_day` reads the walk**

Replace `resolve_day`, from `def resolve_day(` to the end of the file, with:

```python
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
```

- The window is the four days before `target_date`. Their carries onto `target_date` sit in `ledger.carried`, which lists only days that something landed on, so the lookup is `.get(target_date, {})`.
- `target_effective` is still costed against `target.rda`. The target date is the context date, so its base is the overlay's own figure.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_ledger_walk.py tests/test_tracking_api.py tests/test_targets_service.py tests/test_weight_service.py tests/test_weight_api.py tests/test_menstrual_status.py tests/test_cycle_api.py tests/test_preferences_api.py tests/test_planner_api.py -q && uv run ruff check .`
Expected: all PASS, and ruff is clean. These are the suites that read `resolve_day`: Today, the planner, the baseline, and the iron and recalibration warnings. Every one passes unchanged, because its figures are the same as before.

- [ ] **Step 7: Commit**

```bash
git add app/targets/service.py tests/test_ledger_walk.py
git commit -m "refactor(backend): walk the compensation ledger once, and let resolve_day read it

The weekly report needs what Today's ledger already worked out and threw
away: which days were tracked, what each day was carried, and what expired,
in which direction. A second copy of the loop would drift from Today's the
first time either changed, so the loop moves out of resolve_day into
walk_ledger, which records every source day as it goes. Expiry keeps its
direction because a shortfall that expired is what the report calls
uncompensated, while a surplus that expired is not a gap at all.

Plan 7's per-day offset costing moves with it, into base_targets_on, so every
reader costs a day at the recalibration in force on that day, and a target a
condition set keeps the context date's figure as before. load_context gathers
the profile, references, overlay and policies once, so a week's walk loads
them once rather than per day.

resolve_day keeps its signature and its output, figure for figure: the
tracking, weight, planner and cycle suites pass unchanged.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Models and migration

Two per-user tables, one column, one index and a data step. Both tables are keyed to the user and cascade with them, and neither belongs to the profile's child set: a profile save deletes those, and editing a meal time must not unsubscribe a device or forget which reminders already went out. The two unique keys are the load-bearing part: `uq_push_endpoint` is what makes a shared phone remind only its current user (Task 10), and `uq_delivery_user_day_slot` is the whole of "exactly once" (Task 11).

**Files:**
- Create: `app/models/push.py`, `alembic/versions/f2a3b4c5d6e7_reports_and_reminders.py`
- Modify:
  - `app/models/plan.py`: `MealPlan.emphasis`
  - `app/models/diary.py`: the composite index on `MealLog`
  - `app/models/__init__.py`
  - `scripts/e2e_session.py`: `OWNED_MODELS` gains `PushSubscription` and `ReminderDelivery`
- Test: `tests/test_push_models.py` (create)

**Interfaces:**
- Consumes: plan 7's migration head `e1f2a3b4c5d6`; `TimestampedBase`
- Produces:
```python
# uq_push_endpoint (endpoint)
PushSubscription(user_id, endpoint: str, p256dh: str, auth: str, user_agent: str | None)
# uq_delivery_user_day_slot (user_id, local_date, slot); status: sent | failed | no-device
ReminderDelivery(user_id, local_date: date, slot: str, status: str)
MealPlan.emphasis: str        # space-separated codes; "" = none (server_default '')
Index("ix_meal_logs_user_day", "user_id", "logged_on")      # on MealLog
# data: meal_slot_times.reminder_on = false for slot 'snack1' (downgrade: no-op)
```
- Used by: Task 6 (`MealPlan.emphasis`), Task 10 (`PushSubscription`, upsert on `uq_push_endpoint`), Task 11 (`ReminderDelivery`, claimed with `ON CONFLICT ON CONSTRAINT uq_delivery_user_day_slot DO NOTHING RETURNING`), and Tasks 5 and 11 read meal logs through the index.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_push_models.py`:

```python
"""Push subscriptions, reminder claims and the plan's emphasis, on the migrated schema.

A reminder goes out at most once because the database refuses a second claim on
the same user, date and slot -- not because the sender remembers what it sent.
A phone reminds one person because an endpoint is one row. The runner and the
subscribe route stand on these constraints, so they are tested where they live.
"""

import datetime
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.models.plan import MealPlan
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User

DAY = datetime.date(2026, 8, 17)
WEEK = datetime.date(2026, 8, 16)  # a Sunday
ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-one"


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def user(db) -> User:
    return make_user(db, "push")


def device(user: User, endpoint: str = ENDPOINT) -> PushSubscription:
    return PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="p" * 87, auth="a" * 22)


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def rows_of(db, model, user_id: uuid.UUID) -> list:
    return db.scalars(select(model).where(model.user_id == user_id)).all()


def claim(db, user: User, slot: str = "lunch", day: datetime.date = DAY) -> uuid.UUID | None:
    """The runner's claim: the new row's id when this call won the reminder, else None."""
    return db.execute(
        insert(ReminderDelivery)
        .values(user_id=user.id, local_date=day, slot=slot, status="failed")
        .on_conflict_do_nothing(constraint="uq_delivery_user_day_slot")
        .returning(ReminderDelivery.id)
    ).scalar_one_or_none()


def test_an_endpoint_is_one_subscription_whoever_posts_it(db, user):
    db.add(device(user))
    db.flush()
    # The same browser, subscribed from another account, must move -- not duplicate.
    refused(db, device(make_user(db, "other")))


def test_a_user_can_subscribe_several_devices(db, user):
    db.add_all([device(user), device(user, f"{ENDPOINT}-laptop")])
    db.flush()

    rows = rows_of(db, PushSubscription, user.id)
    assert len(rows) == 2
    assert {row.user_agent for row in rows} == {None}


def test_a_reminder_is_claimed_once(db, user):
    assert claim(db, user) is not None
    # A restart, an overlapping cron run or a second instance: each loses the insert.
    assert claim(db, user) is None


def test_each_slot_and_each_day_is_its_own_claim(db, user):
    assert claim(db, user, "lunch", DAY) is not None
    assert claim(db, user, "dinner", DAY) is not None
    assert claim(db, user, "lunch", DAY + datetime.timedelta(days=1)) is not None


def test_one_users_claim_does_not_block_another(db, user):
    assert claim(db, user) is not None
    assert claim(db, make_user(db, "other")) is not None


def test_devices_and_claims_go_with_their_user(db, user):
    user_id = user.id
    db.add(device(user))
    db.flush()
    assert claim(db, user) is not None

    db.delete(user)
    db.flush()

    assert rows_of(db, PushSubscription, user_id) == []
    assert rows_of(db, ReminderDelivery, user_id) == []


def test_a_new_plan_has_no_emphasis(db, user):
    plan = MealPlan(user_id=user.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    assert plan.emphasis == ""


def test_a_plan_stored_before_emphasis_existed_reads_as_none(db, user):
    """The migration's server default is the backfill every existing plan gets."""
    plan_id = uuid.uuid4()
    db.execute(
        text(
            "insert into meal_plans (id, user_id, week_start, seed) "
            "values (:id, :user_id, :week_start, 1)"
        ),
        {"id": plan_id, "user_id": user.id, "week_start": WEEK},
    )
    emphasis = db.scalar(text("select emphasis from meal_plans where id = :id"), {"id": plan_id})
    assert emphasis == ""


def test_meal_logs_are_indexed_by_user_and_day(db):
    indexes = inspect(db.connection()).get_indexes("meal_logs")
    columns = {index["name"]: index["column_names"] for index in indexes}
    assert columns["ix_meal_logs_user_day"] == ["user_id", "logged_on"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_push_models.py -q`
Expected: FAIL: `ModuleNotFoundError: No module named 'app.models.push'`

- [ ] **Step 3: Write the models**

Create `app/models/push.py`:

```python
import datetime
import uuid

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class PushSubscription(TimestampedBase):
    """One browser's web-push endpoint, and the keys a payload is encrypted to.

    Unique on the endpoint across every user, not per user: the push service mints
    one endpoint per browser install, so the endpoint names a device. When a second
    account subscribes the same browser, the row moves to that account -- a shared
    phone reminds whoever subscribed it last, and never shows one person's meal
    nudges to another.

    Not one of the profile's child tables, and it must never become one: a profile
    save deletes those, and editing a meal time must not unsubscribe every device.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_endpoint"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The push service's URL for this browser. Text, because nothing bounds its length.
    endpoint: Mapped[str] = mapped_column(Text)
    # The browser's P-256 public key and auth secret (RFC 8291), base64url-encoded:
    # 87 and 22 characters in practice.
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    # Which device this is, for a person reading their own list. A User-Agent header
    # has no length limit, so whatever stores it cuts it to 300 characters first.
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ReminderDelivery(TimestampedBase):
    """A claim on one reminder: one user, one local date, one slot.

    Inserted before anything is sent, with INSERT ... ON CONFLICT DO NOTHING
    RETURNING, and only the call that gets a row back sends. The unique key is the
    whole of "exactly once": a restart, an overlapping cron run or a second instance
    each lose the insert, instead of trusting a memory of what already went out.

    The price is that a failed send is not retried. For a nudge, at most once is the
    right side to err on: a reminder sent twice is noise, and a retry that lands an
    hour late is about a meal already eaten.
    """

    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", "slot", name="uq_delivery_user_day_slot"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The user's local date, matching `MealLog.logged_on`: the slot's day is theirs.
    local_date: Mapped[datetime.date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(12))
    # sent | failed | no-device: what the channel answered. The claim goes in before
    # the send, as failed, and is corrected once the channel answers -- so a crash
    # between the two reads as not delivered rather than as delivered.
    status: Mapped[str] = mapped_column(String(12))
```

In `app/models/plan.py`, add to `MealPlan` after `seed: Mapped[int] = mapped_column(Integer)`:

```python
    # Space-separated nutrient codes the previous week's report suggested; the planner
    # weighs them EMPHASIS_FACTOR more for this week. Empty string = none. Stored
    # rather than recomputed, so a swap or a re-plan keeps the emphasis the week was
    # generated with; only a regenerate recomputes it.
    emphasis: Mapped[str] = mapped_column(String(200), default="", nullable=False)
```

`String` is already imported there.

In `app/models/diary.py`, replace the import

```python
from sqlalchemy import Boolean, Date, Float, ForeignKey, String, UniqueConstraint
```

with

```python
from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, String, UniqueConstraint
```

and add to `MealLog`, directly after `__tablename__ = "meal_logs"`:

```python
    # The ledger walk, the weekly report and the reminder runner all read one user's
    # entries on one date, many times over in a single request or tick.
    __table_args__ = (Index("ix_meal_logs_user_day", "user_id", "logged_on"),)
```

Leave the existing `index=True` on `user_id` and `logged_on` as it is: `alembic check` compares every index, and those two stay in the schema.

In `app/models/__init__.py`, add

```python
from app.models.push import PushSubscription, ReminderDelivery
```

after the closing `)` of the `app.models.profile` import, and before the `app.models.reference` import. In `__all__`, add `"PushSubscription"` between `"Profile"` and `"RdaReference"`, and `"ReminderDelivery"` between `"RdaReference"` and `"UpperLimit"` (RUF022 order).

- [ ] **Step 4: Write the migration**

Create `alembic/versions/f2a3b4c5d6e7_reports_and_reminders.py`:

```python
"""reports and reminders

Two per-user tables, one column, one index and one data step.

`push_subscriptions` holds one row per browser endpoint, with the keys a push
payload is encrypted to. The endpoint is unique across users, not per user: it
names a device, and a device re-subscribed by another account moves to it.

`reminder_deliveries` is the exactly-once claim on a reminder: one row per user,
local date and slot, inserted before anything is sent. The unique key is what a
restart, an overlapping cron run or a second instance collides with.

`meal_plans.emphasis` holds the nutrients the previous week's report suggested,
as space-separated codes. Its server default is the backfill: every plan stored
so far was generated before there was a report to take an emphasis from.

`ix_meal_logs_user_day` serves the read the ledger walk, the report and the
reminder runner repeat most: one user's entries on one date.

The data step turns the mid-morning snack's reminder off, the spec's own example
of a reminder that should not nag someone who rarely eats that snack.
`reminder_on` has defaulted to true since the column was added and no screen has
ever written it, so no row holds a choice anyone made. The downgrade leaves it
alone: by then a user may have set it on the Reminders screen, and the two
cannot be told apart.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-24

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
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
        "push_subscriptions",
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        unique=("endpoint",),
        constraint="uq_push_endpoint",
    )
    _owned(
        "reminder_deliveries",
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        unique=("user_id", "local_date", "slot"),
        constraint="uq_delivery_user_day_slot",
    )
    # `server_default` is required, not cosmetic: the column is NOT NULL and every
    # existing plan needs a value. Empty is right, since none had a report behind it.
    op.add_column(
        "meal_plans",
        sa.Column("emphasis", sa.String(length=200), nullable=False, server_default=""),
    )
    op.create_index("ix_meal_logs_user_day", "meal_logs", ["user_id", "logged_on"], unique=False)
    op.execute(sa.text("UPDATE meal_slot_times SET reminder_on = false WHERE slot = 'snack1'"))


def downgrade() -> None:
    """Downgrade schema."""
    # The reminder_on data step is not reversed; the module docstring says why.
    op.drop_index("ix_meal_logs_user_day", table_name="meal_logs")
    op.drop_column("meal_plans", "emphasis")
    for name in ("reminder_deliveries", "push_subscriptions"):
        op.drop_index(op.f(f"ix_{name}_user_id"), table_name=name)
        op.drop_table(name)
```

Then migrate both databases and check that the models and migration agree:

```bash
DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor_test \
  uv run alembic upgrade head
uv run alembic upgrade head
uv run alembic check
```

Expected: `No new upgrade operations detected.` If `check` reports a difference, fix the **migration** to match the model. `check` does not compare server defaults, so the `''` on `meal_plans.emphasis` is not reported; the model's `default=""` covers rows the ORM writes, and the server default covers the rows that already exist, as `meal_slot_times.is_enabled` does. Then prove the downgrade works and return to head:

```bash
uv run alembic downgrade -1 && uv run alembic upgrade head
```

The test database has no rows when it migrates, so no test can see the data step. Check it on the development database instead:

```bash
uv run python - <<'PY'
from sqlalchemy import text

from app.db import SessionLocal

with SessionLocal() as db:
    print(db.scalar(text(
        "select count(*) from meal_slot_times where slot = 'snack1' and reminder_on"
    )))
PY
```

Expected: `0`. Run this before saving any profile. Until Task 9, a profile save rewrites every slot's `reminder_on` from the payload, whose default is still true.

- [ ] **Step 5: Reset the new tables in the end-to-end run**

In `scripts/e2e_session.py`, add

```python
from app.models.push import PushSubscription, ReminderDelivery
```

after the closing `)` of the `app.models.profile` import, and before the `app.models.user` import. Replace the module docstring's `--reset` paragraph with:

```
`--reset` deletes everything the user has logged, planned, answered and
subscribed, so a run starts from onboarding. It never touches any user but this
one.
```

Replace the comment above `OWNED_MODELS`, and the tuple itself, with:

```python
# Everything the walk writes. Each is keyed on user_id; meal_plan_items goes with
# its plan through the foreign key's ON DELETE CASCADE. Missing a table here means
# a second run starts from the first run's leftovers -- a weigh-in history that
# grows every run, cycle tracking already switched on, or a device still
# subscribed to the last run's reminders.
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
    ReminderDelivery,
    PushSubscription,
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

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_push_models.py tests/test_tracking_api.py tests/test_planner_api.py -q && uv run ruff check .`
Expected: all PASS, ruff clean. The tracking and planner suites pass unchanged. The planner builds plans as `MealPlan(user_id=..., week_start=..., seed=...)`, which takes the empty emphasis by default, and nothing reads the emphasis until Task 6.

- [ ] **Step 7: Commit**

```bash
git add app/models/push.py app/models/plan.py app/models/diary.py app/models/__init__.py \
  alembic/versions/f2a3b4c5d6e7_reports_and_reminders.py scripts/e2e_session.py \
  tests/test_push_models.py
git commit -m "feat(backend): add the push subscription and reminder delivery tables

push_subscriptions has one row per browser endpoint, unique across users.
An endpoint names a device, so when another account subscribes the same
phone, the row moves to that account instead of reminding both.
reminder_deliveries is the exactly-once claim: one row per user, local date
and slot, inserted before a reminder is sent. A restart, an overlapping cron
run or a second instance runs into the unique key, so no process has to
remember what already went out.

meal_plans gains emphasis, the nutrients the previous week's report
suggested. It is stored so that a swap or a re-plan keeps the emphasis the
week was generated with. meal_logs gains a (user_id, logged_on) index for
the one-user, one-day read that the ledger walk, the report and the
reminder runner repeat.

A data step turns the mid-morning snack's reminder off. No screen has ever
written reminder_on, so every row holds the column default rather than a
choice. That snack is the spec's own example of a reminder that should not
nag.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The report's arithmetic (pure)

This task writes everything the weekly report decides, as pure functions over plain data: what counts as met on a day, which shortfalls expired and why, and which nutrients and dishes to suggest for next week. Task 5 feeds it from the ledger walk and the diary, Task 6 reads its suggestions through Task 5, and Task 7 counts days met from its rows. Keeping it free of the database means every rule in the Decisions ("The report") is pinned by a test that runs in milliseconds.

**Files:**
- Create: `app/reports/__init__.py` (empty), `app/reports/summary.py`
- Test: `tests/test_report_summary.py` (create)

**Interfaces:**
- Consumes: `app.planner.rules` as it stands: `Candidate`, `DayRules`, `FoodRef`, `allowed_by_diet`, `is_avoided`, `nutrients_for`. Nothing from Tasks 1–3.
- Produces (used by Tasks 5 and 7):
```python
UNCOMPENSATED_MIN_SHARE = 0.01
SUGGESTION_SHORTFALL_SHARE = 0.90
SUGGESTION_MIN_COVERAGE = 0.5
SUGGESTION_MIN_DAYS = 3
MAX_SUGGESTED_NUTRIENTS = 3
MAX_SUGGESTED_FOODS = 3
EXCLUDED_FROM_GAPS = frozenset({"energy"})

@dataclass(frozen=True) class NutrientMeta:
    code; display_name; unit; category; kind; is_compensable: bool; carry_cap_fraction: float
@dataclass(frozen=True) class DayFacts:
    date; consumed; coverage; base; ear: dict[str, float | None]; effective;
    tul: dict[str, float | None]; expired_shortfall
@dataclass(frozen=True) class NutrientWeek:
    code; display_name; unit; category; kind; measured_days; target_total;
    ear_total: float | None; consumed_total; days_met; days_over_limit; coverage
@dataclass(frozen=True) class Gap:
    code; display_name; unit; amount; reason_code: str; reason: str   # not_compensable | cap

def is_met(kind, consumed, ear, effective, tul) -> bool
def summarise(days: Sequence[DayFacts], meta: dict[str, NutrientMeta]) -> list[NutrientWeek]
def uncompensated(days, meta, held_steady: frozenset[str]) -> list[Gap]
def nutrients_to_suggest(weeks: Sequence[NutrientWeek], tracked_days: int,
                         excluded: frozenset[str]) -> list[NutrientWeek]
def foods_for(code: str, pool: Sequence[Candidate], profile_diet: str,
              avoided: Sequence[FoodRef]) -> list[Candidate]
def suggestion_text(week: NutrientWeek, foods: Sequence[Candidate]) -> str
```

What Task 5 must put into these, so the arithmetic reads the figures Today shows:
- `NutrientMeta.kind` is the target's `kind` (`target` | `ceiling`); the nutrients table has no such column. `is_compensable` is the nutrients table's own flag, and `carry_cap_fraction` is `compensation.carry_cap_for(code)`.
- `DayFacts.ear` is the target's EAR, as Today shows it: `None` for energy, not the ledger policy's energy floor. `base`, `effective` and `expired_shortfall` come straight from the day's `LedgerDay`; `consumed` and `coverage` from the diary.
- Only elapsed, tracked days become `DayFacts`. A code with no entry in a day's `base` is not measured on that day, so a nutrient without a target never gets a row. Cholesterol, for example, has no reference row, and gets a target only through the high-cholesterol overlay.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report_summary.py`:

```python
"""The weekly report's arithmetic, on plain data.

What counts as met, which shortfalls were never made up and why, and what to suggest
for next week. No database: `app.reports.service` feeds these functions, and the
numbers here are chosen so each test has one obvious answer. Calcium is 1,000 mg a
day with an 800 mg EAR and a 2,500 mg upper limit, as ICMR-NIN 2020 has it.
"""

import datetime
import uuid

import pytest

from app.planner.rules import Candidate, FoodRef, Portion
from app.reports.summary import (
    DayFacts,
    Gap,
    NutrientMeta,
    NutrientWeek,
    foods_for,
    is_met,
    nutrients_to_suggest,
    suggestion_text,
    summarise,
    uncompensated,
)

SUNDAY = datetime.date(2026, 9, 13)


def meta(
    code: str,
    display_name: str,
    unit: str,
    category: str,
    kind: str = "target",
    *,
    compensable: bool = True,
    cap: float = 0.30,
) -> NutrientMeta:
    return NutrientMeta(
        code=code,
        display_name=display_name,
        unit=unit,
        category=category,
        kind=kind,
        is_compensable=compensable,
        carry_cap_fraction=cap,
    )


META = {
    m.code: m
    for m in (
        meta("energy", "Energy", "kcal", "macro"),
        meta("protein", "Protein", "g", "macro", compensable=False),
        meta("fibre", "Dietary fibre", "g", "macro", cap=0.25),
        meta("calcium", "Calcium", "mg", "mineral"),
        meta("sodium", "Sodium", "mg", "mineral", "ceiling", compensable=False),
        meta("vitamin_k", "Vitamin K", "ug", "vitamin"),
    )
}

BASE = {
    "energy": 2000.0,
    "protein": 54.0,
    "fibre": 30.0,
    "calcium": 1000.0,
    "sodium": 2000.0,
    "vitamin_k": 55.0,
}
EAR = {"protein": 43.0, "calcium": 800.0}
TUL = {"calcium": 2500.0}


def day(
    n: int,
    consumed: dict[str, float],
    *,
    coverage: dict[str, float] | None = None,
    effective: dict[str, float] | None = None,
    expired: dict[str, float] | None = None,
) -> DayFacts:
    """Day n of the week (0 = Sunday). Every code consumed is fully measured unless
    `coverage` says otherwise, and the effective targets are the base ones unless a
    carry moved them."""
    return DayFacts(
        date=SUNDAY + datetime.timedelta(days=n),
        consumed=consumed,
        coverage=coverage if coverage is not None else dict.fromkeys(consumed, 1.0),
        base=dict(BASE),
        ear={code: EAR.get(code) for code in BASE},
        effective={**BASE, **(effective or {})},
        tul={code: TUL.get(code) for code in BASE},
        expired_shortfall=expired or {},
    )


def row(weeks: list[NutrientWeek], code: str) -> NutrientWeek:
    return next(week for week in weeks if week.code == code)


# --- what counts as met ------------------------------------------------------------------------


def test_a_target_nutrient_is_met_from_its_ear():
    # 850 mg is short of the 1,000 mg target but clear of the 800 mg adequacy floor.
    assert is_met("target", 850.0, 800.0, 1000.0, 2500.0)


def test_under_the_ear_is_a_miss():
    assert not is_met("target", 790.0, 800.0, 1000.0, 2500.0)


def test_without_an_ear_the_effective_target_is_the_floor():
    # Fibre carrying 6 g in from a short day: 32 g no longer reaches it.
    assert not is_met("target", 32.0, None, 36.0, None)
    assert is_met("target", 36.0, None, 36.0, None)


def test_going_over_the_target_is_not_a_miss():
    assert is_met("target", 1800.0, 800.0, 1000.0, 2500.0)


def test_reaching_the_upper_limit_is_a_miss():
    # Reaching a limit exactly is already "above the limit" on Today
    # (status.ts: consumed >= limit).
    assert is_met("target", 2499.0, 800.0, 1000.0, 2500.0)
    assert not is_met("target", 2500.0, 800.0, 1000.0, 2500.0)
    assert not is_met("target", 2600.0, 800.0, 1000.0, 2500.0)


def test_a_low_sodium_day_is_not_a_miss():
    assert is_met("ceiling", 300.0, None, 2000.0, None)
    assert is_met("ceiling", 1999.0, None, 2000.0, None)
    assert not is_met("ceiling", 2000.0, None, 2000.0, None)
    assert not is_met("ceiling", 2001.0, None, 2000.0, None)


def test_a_ceiling_lowered_by_yesterdays_surplus_is_the_one_judged():
    # After a 4,000 mg day the next two ceilings drop to 1,400 mg (spec manual step 5).
    assert not is_met("ceiling", 1600.0, None, 1400.0, None)


# --- the week, per nutrient --------------------------------------------------------------------

# Calcium is met on Sunday, missed on Monday and over the limit on Tuesday, with the
# ledger's carries raising Monday's and Tuesday's targets. On Wednesday nothing logged
# had a calcium figure.
CALCIUM_WEEK = [
    day(0, {"energy": 1900.0, "calcium": 900.0}),
    day(
        1,
        {"energy": 1700.0, "calcium": 700.0},
        coverage={"energy": 1.0, "calcium": 0.5},
        effective={"calcium": 1050.0},
    ),
    day(
        2,
        {"energy": 2100.0, "calcium": 2600.0},
        coverage={"energy": 1.0, "calcium": 0.9},
        effective={"calcium": 1225.0},
    ),
    day(3, {"energy": 150.0}),
]


def test_only_measured_days_count():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert calcium.measured_days == 3
    assert calcium.consumed_total == pytest.approx(4200.0)


def test_the_target_total_sums_base_targets_not_effective_ones():
    # Monday's extra 50 mg is half of Sunday's 100 mg shortfall being made up:
    # summing effective targets would count that shortfall twice.
    assert row(summarise(CALCIUM_WEEK, META), "calcium").target_total == pytest.approx(3000.0)


def test_the_ear_total_sums_the_ear_over_measured_days():
    weeks = summarise(CALCIUM_WEEK, META)

    assert row(weeks, "calcium").ear_total == pytest.approx(2400.0)
    assert row(weeks, "energy").ear_total is None


def test_days_met_and_days_over_the_limit_are_counted_apart():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert calcium.days_met == 1
    assert calcium.days_over_limit == 1


def test_coverage_is_the_mean_over_measured_days():
    assert row(summarise(CALCIUM_WEEK, META), "calcium").coverage == pytest.approx(0.8)


def test_a_nutrient_nothing_measured_is_left_out():
    codes = [week.code for week in summarise(CALCIUM_WEEK, META)]
    assert "vitamin_k" not in codes
    assert "protein" not in codes


def test_the_row_carries_the_nutrients_own_names():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert (calcium.display_name, calcium.unit, calcium.category, calcium.kind) == (
        "Calcium",
        "mg",
        "mineral",
        "target",
    )


def test_a_ceiling_counts_days_under_it():
    days = [
        day(0, {"sodium": 4000.0}),
        day(1, {"sodium": 1600.0}, effective={"sodium": 1400.0}),
        day(2, {"sodium": 1300.0}, effective={"sodium": 1400.0}),
    ]
    sodium = row(summarise(days, META), "sodium")

    assert sodium.days_met == 1
    assert sodium.target_total == pytest.approx(6000.0)


def test_nutrients_read_macros_then_minerals_then_vitamins():
    everything = dict.fromkeys(BASE, 1.0)
    codes = [week.code for week in summarise([day(0, everything)], META)]

    assert codes == ["fibre", "energy", "protein", "calcium", "sodium", "vitamin_k"]


def test_a_code_without_a_target_that_day_is_not_measured_against_one():
    cholesterol = meta("cholesterol", "Cholesterol", "mg", "macro", "ceiling")
    days = [day(0, {"cholesterol": 300.0})]

    assert summarise(days, {"cholesterol": cholesterol}) == []


def test_no_days_give_no_rows():
    assert summarise([], META) == []


# --- what was never made up --------------------------------------------------------------------


def test_a_shortfall_beyond_the_cap_is_uncompensated():
    # 100 mg on Sunday is 900 short; the next two days can take 300 each, so 300
    # expires. Monday, raised to 1,300, falls 900 short again and 300 more expires.
    days = [
        day(0, {"calcium": 100.0}, expired={"calcium": 300.0}),
        day(1, {"calcium": 400.0}, effective={"calcium": 1300.0}, expired={"calcium": 300.0}),
    ]

    assert uncompensated(days, META, frozenset()) == [
        Gap(
            code="calcium",
            display_name="Calcium",
            unit="mg",
            amount=600.0,
            reason_code="cap",
            reason="Beyond the 30% a day can carry, so it expired.",
        )
    ]


def test_fibre_names_its_own_tighter_cap():
    # 10 g of 30 is 20 short; 7.5 g a day for two days carries 15, and 5 expires.
    [gap] = uncompensated([day(0, {"fibre": 10.0}, expired={"fibre": 5.0})], META, frozenset())

    assert gap.amount == pytest.approx(5.0)
    assert gap.reason == "Beyond the 25% a day can carry, so it expired."


def test_a_protein_shortfall_is_never_carried():
    # 30 g of a 54 g target: all 24 g short expire on the day.
    [gap] = uncompensated([day(0, {"protein": 30.0}, expired={"protein": 24.0})], META, frozenset())

    assert gap.reason_code == "not_compensable"
    assert gap.reason == "Protein has no storage pool, so a short day is not carried forward."
    assert gap.amount == pytest.approx(24.0)


def test_another_nutrient_without_a_store_gets_the_general_reason():
    zinc = meta("zinc", "Zinc", "mg", "mineral", compensable=False)
    facts = DayFacts(
        date=SUNDAY,
        consumed={"zinc": 5.0},
        coverage={"zinc": 1.0},
        base={"zinc": 17.0},
        ear={"zinc": 14.0},
        effective={"zinc": 17.0},
        tul={"zinc": 40.0},
        expired_shortfall={"zinc": 12.0},
    )

    [gap] = uncompensated([facts], {"zinc": zinc}, frozenset())

    assert gap.reason == "Zinc is not carried forward: the body has no store of it to draw on."


def test_energy_is_never_reported_as_not_made_up():
    days = [day(0, {"energy": 200.0}, expired={"energy": 600.0})]
    assert uncompensated(days, META, frozenset()) == []


def test_a_nutrient_held_steady_is_never_reported():
    # On warfarin vitamin K is not averaged, so its whole shortfall "expires" by design.
    days = [day(0, {"vitamin_k": 20.0}, expired={"vitamin_k": 35.0})]

    assert uncompensated(days, META, frozenset({"vitamin_k"})) == []
    assert [gap.code for gap in uncompensated(days, META, frozenset())] == ["vitamin_k"]


def test_a_low_sodium_day_is_not_a_gap():
    # The ledger does record it as expired: sodium never carries a shortfall.
    days = [day(0, {"sodium": 500.0}, expired={"sodium": 1500.0})]
    assert uncompensated(days, META, frozenset()) == []


@pytest.mark.parametrize(("expired", "reported"), [(19.9, False), (20.0, True)])
def test_an_expiry_under_one_percent_of_the_week_is_left_out(expired, reported):
    # Two measured days of calcium: 2,000 mg of target, so the line is 20 mg. Sunday
    # falls 600 mg short plus the expiry: the carries take 600, and the rest expires.
    days = [
        day(0, {"calcium": 400.0 - expired}, expired={"calcium": expired}),
        day(1, {"calcium": 1300.0}, effective={"calcium": 1300.0}),
    ]
    assert bool(uncompensated(days, META, frozenset())) is reported


def test_gaps_follow_the_reports_order():
    days = [
        day(
            0,
            {"calcium": 100.0, "protein": 30.0},
            expired={"calcium": 300.0, "protein": 24.0},
        )
    ]
    assert [gap.code for gap in uncompensated(days, META, frozenset())] == ["protein", "calcium"]


# --- what to suggest ---------------------------------------------------------------------------


def week(
    code: str = "calcium",
    *,
    display_name: str | None = None,
    kind: str = "target",
    measured_days: int = 7,
    target_total: float = 7000.0,
    consumed_total: float = 4200.0,
    coverage: float = 0.9,
) -> NutrientWeek:
    return NutrientWeek(
        code=code,
        display_name=display_name or code.replace("_", " ").capitalize(),
        unit="mg",
        category="mineral",
        kind=kind,
        measured_days=measured_days,
        target_total=target_total,
        ear_total=None,
        consumed_total=consumed_total,
        days_met=0,
        days_over_limit=0,
        coverage=coverage,
    )


def suggested(
    weeks: list[NutrientWeek], tracked_days: int = 7, excluded: frozenset[str] = frozenset()
) -> list[str]:
    return [w.code for w in nutrients_to_suggest(weeks, tracked_days, excluded)]


def test_a_week_well_short_is_suggested():
    assert suggested([week(consumed_total=4200.0)]) == ["calcium"]


@pytest.mark.parametrize(("consumed", "codes"), [(6299.0, ["calcium"]), (6300.0, [])])
def test_ninety_percent_of_the_week_is_enough(consumed, codes):
    assert suggested([week(consumed_total=consumed)]) == codes


def test_the_worst_ratio_comes_first_and_three_at_most():
    weeks = [
        week("calcium", consumed_total=4200.0),  # 60%
        week("iron", consumed_total=2800.0),  # 40%
        week("fibre", consumed_total=5600.0),  # 80%
        week("vitamin_b12", consumed_total=3500.0),  # 50%
    ]
    assert suggested(weeks) == ["iron", "vitamin_b12", "calcium"]


@pytest.mark.parametrize(("measured", "codes"), [(3, []), (4, ["calcium"])])
def test_it_must_be_measured_on_half_the_tracked_days(measured, codes):
    assert suggested([week(measured_days=measured)], tracked_days=7) == codes


@pytest.mark.parametrize(("measured", "codes"), [(2, []), (3, ["calcium"])])
def test_it_must_be_measured_on_three_days_at_least(measured, codes):
    # Half of four tracked days is two, but two days say too little.
    assert suggested([week(measured_days=measured)], tracked_days=4) == codes


@pytest.mark.parametrize(("coverage", "codes"), [(0.49, []), (0.5, ["calcium"])])
def test_a_thinly_measured_nutrient_is_not_suggested(coverage, codes):
    assert suggested([week(coverage=coverage)]) == codes


def test_energy_and_ceilings_are_never_suggested():
    weeks = [week("energy", consumed_total=1000.0), week("sodium", kind="ceiling")]
    assert suggested(weeks) == []


def test_the_callers_exclusions_are_never_suggested():
    # Potassium on a potassium-sparing drug (spec manual step 7b).
    weeks = [week("potassium", consumed_total=1000.0), week("calcium")]
    assert suggested(weeks, excluded=frozenset({"potassium"})) == ["calcium"]


# --- which dishes ------------------------------------------------------------------------------


def dish(
    name: str,
    per_100g: dict[str, float],
    *,
    diet: str = "vegetarian",
    grams: float = 200.0,
    ingredients: tuple[str, ...] = (),
    dish_id: uuid.UUID | None = None,
) -> Candidate:
    return Candidate(
        dish_id=dish_id or uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset({"lunch", "dinner"}),
        diet=diet,
        ingredient_ids=frozenset(uuid.uuid5(uuid.NAMESPACE_DNS, i) for i in ingredients),
        ingredient_names=ingredients,
        per_100g=per_100g,
        portions=(Portion(grams, "cup", 1.0, "1 cup"),),
        default_grams=grams,
    )


# Calcium per default portion: paneer 400 mg, fish 330, ragi 300, curd rice 162.5,
# payasam 120, egg curry 100, idli none at all. B12: egg curry 1.2 ug, curd rice 0.5.
PANEER = dish(
    "Paneer butter masala", {"calcium": 200.0}, ingredients=("Paneer", "Butter", "Tomato")
)
FISH_FRY = dish("Fish fry", {"calcium": 220.0}, diet="fishetarian", grams=150.0)
RAGI_MUDDE = dish("Ragi mudde", {"calcium": 120.0}, grams=250.0)
CURD_RICE = dish("Curd rice", {"calcium": 65.0, "vitamin_b12": 0.2}, grams=250.0)
PAYASAM = dish("Moong dal payasam", {"calcium": 60.0})
EGG_CURRY = dish("Egg curry", {"calcium": 50.0, "vitamin_b12": 0.6}, diet="eggetarian")
IDLI = dish("Idli", {"energy": 130.0})
POOL = [IDLI, EGG_CURRY, PAYASAM, CURD_RICE, RAGI_MUDDE, FISH_FRY, PANEER]

NO_PANEER = (FoodRef(label="paneer"),)


def dish_names(candidates: list[Candidate]) -> list[str]:
    return [c.name for c in candidates]


def test_dishes_are_ranked_by_the_nutrient_in_a_default_portion():
    assert dish_names(foods_for("calcium", POOL, "vegetarian", ())) == [
        "Paneer butter masala",
        "Ragi mudde",
        "Curd rice",
    ]


def test_an_avoided_ingredient_is_never_suggested():
    assert dish_names(foods_for("calcium", POOL, "vegetarian", NO_PANEER)) == [
        "Ragi mudde",
        "Curd rice",
        "Moong dal payasam",
    ]


def test_an_avoided_dish_picked_from_search_is_never_suggested():
    avoided = (FoodRef(label="Ragi mudde", food_id=RAGI_MUDDE.dish_id, food_kind="dish"),)
    assert dish_names(foods_for("calcium", POOL, "vegetarian", avoided)) == [
        "Paneer butter masala",
        "Curd rice",
        "Moong dal payasam",
    ]


def test_the_diet_decides_what_may_be_suggested():
    assert dish_names(foods_for("calcium", POOL, "fishetarian", NO_PANEER)) == [
        "Fish fry",
        "Ragi mudde",
        "Curd rice",
    ]
    assert dish_names(foods_for("vitamin_b12", POOL, "vegetarian", ())) == ["Curd rice"]


def test_a_dish_without_the_nutrient_is_not_suggested():
    # Only two dishes carry any B12, so an eggetarian is offered two, not three.
    assert dish_names(foods_for("vitamin_b12", POOL, "eggetarian", ())) == [
        "Egg curry",
        "Curd rice",
    ]


def test_equal_dishes_go_by_name_whatever_their_case():
    # A dish the user typed in keeps the case they typed it in.
    pool = [dish("Beetroot poriyal", {"calcium": 50.0}), dish("avial", {"calcium": 50.0})]
    assert dish_names(foods_for("calcium", pool, "vegetarian", ())) == [
        "avial",
        "Beetroot poriyal",
    ]


def test_a_household_copy_of_a_dish_is_not_named_twice():
    copy = dish("Curd Rice", {"calcium": 70.0}, grams=250.0, dish_id=uuid.uuid4())
    chosen = foods_for("calcium", [*POOL, copy], "vegetarian", NO_PANEER)

    assert dish_names(chosen) == ["Ragi mudde", "Curd Rice", "Moong dal payasam"]
    assert chosen[1].dish_id == copy.dish_id


# --- the sentence ------------------------------------------------------------------------------


def test_the_suggestion_names_its_dishes():
    text = suggestion_text(week(display_name="Calcium"), [RAGI_MUDDE, CURD_RICE, PAYASAM])
    assert text == (
        "Calcium fell short this week. "
        "Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam."
    )


def test_two_dishes_are_listed_with_a_comma_in_the_order_given():
    text = suggestion_text(week(display_name="Calcium"), [CURD_RICE, RAGI_MUDDE])
    assert text == "Calcium fell short this week. Dishes that carry it: Curd rice, Ragi mudde."


def test_one_dish_stands_alone():
    text = suggestion_text(week("vitamin_b12", display_name="Vitamin B12"), [CURD_RICE])
    assert text == "Vitamin B12 fell short this week. Dishes that carry it: Curd rice."


def test_with_no_dishes_the_shortfall_is_still_said():
    assert suggestion_text(week(display_name="Calcium"), []) == "Calcium fell short this week."


def test_dish_names_keep_their_own_capitals():
    mysore = dish("Mysore masala dosa", {"calcium": 10.0})
    text = suggestion_text(week(display_name="Calcium"), [RAGI_MUDDE, mysore])
    assert text == "Calcium fell short this week. Dishes that carry it: Ragi mudde, Mysore masala dosa."
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_report_summary.py -q`
Expected: FAIL: a collection error, `ModuleNotFoundError: No module named 'app.reports'`

- [ ] **Step 3: Write the module**

Create `app/reports/__init__.py` (empty) and `app/reports/summary.py`:

```python
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


```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_report_summary.py -q && uv run ruff check app/reports tests/test_report_summary.py`
Expected: `52 passed` (47 tests, five of them parametrised over two cases), ruff clean. Nothing else imports the module yet, so no other suite can move.

- [ ] **Step 5: Commit**

```bash
git add app/reports/__init__.py app/reports/summary.py tests/test_report_summary.py
git commit -m "feat(backend): add the weekly report's arithmetic -- met days, gaps, suggestions

Pure functions over the days a week's ledger walk hands them. Every figure
is over measured days only, so a gap in the food tables never reads as a
deficit. The target total sums base targets: a shortfall made up later
raised that later day's effective target, and summing those would count
it twice. A day is met on Today's band -- from the EAR and under the
upper limit, or under a ceiling that a surplus may have lowered.

Uncompensated gaps are the shortfalls that expired, for target nutrients
only, each with its reason: protein has no store, and anything else hit
its carry cap. Energy is never reported, because 'calories not made up'
works against a weight-loss goal, and neither is anything held steady,
which is not averaged by design.

Suggestions are the three worst well-measured shortfalls under 90% of the
week's target, never energy, anything held steady or the caller's safety
exclusions. Each comes with up to three dishes that the diet and the
avoided foods allow, ranked by that nutrient per default portion, through
the planner's own rules so a suggestion never names a dish the plan would
refuse.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: The report service and API

This task assembles the report and puts it behind HTTP. The service gathers one week's inputs and hands them to Task 4's pure summary: one ledger walk, one pass over each tracked day's diary, the slot states and the stored plan. The router rounds the figures and serialises them. The diary gains two readers that the report, and later the reminders, share with the diary screen. So a slot the screen shows as skipped is the slot the report counts as skipped, and the rules for that live in one place.

**Files:**
- Create: `app/reports/service.py`, `app/reports/router.py`
- Modify:
  - `app/diary/service.py`: `DayBreakdown`, `day_breakdown`, `slot_states`, and a shared `_shares`
  - `app/diary/router.py`: `read_diary` reads `slot_states`
  - `app/main.py`: the reports router
- Test: `tests/test_reports_api.py` (create)

**Interfaces:**
- Consumes:
  - Task 2: `targets.load_context`, `targets.walk_ledger`, `targets.base_targets_on`, `targets.TargetContext`, and `LedgerDay`'s fields (`tracked`, `consumed`, `base`, `effective`, `expired_shortfall`). Also `targets.COMPENSATION_WINDOW_DAYS`, which is unchanged.
  - Task 4: from `app.reports.summary`, the types `DayFacts`, `NutrientMeta`, `NutrientWeek` and `Gap`, and the functions `summarise`, `uncompensated`, `nutrients_to_suggest`, `foods_for` and `suggestion_text`.
  - Task 3: `MealPlan.emphasis` has an ORM default, so the tests can write plans directly.
  - Existing:
    - `planner.service`: `get_plan`, `load_pool` and `week_start_for`;
    - `planner.rules`: `sunday_index` and `FoodRef`;
    - `nutrition_core.conditions.POTASSIUM_SPARING_DRUGS`.
- Produces:
```python
# app/diary/service.py
@dataclass(frozen=True)
class DayBreakdown:
    consumed: dict[str, float]          # == consumed_on(day)
    coverage: dict[str, float]          # == coverage_on(day)
    estimated_energy: float             # energy from entries with is_estimated
    logged_slots: frozenset[str]
def day_breakdown(db, user, on_date) -> DayBreakdown     # one list_entries call
def slot_states(db, user, on_date) -> dict[str, str]
    # slot -> logged | skipped | empty, in SLOTS order; a disabled, empty slot is left out

# app/reports/service.py
class NoProfile(LookupError)
@dataclass(frozen=True) class ReportDayView: date; weekday; state; energy_kcal; target_kcal
@dataclass(frozen=True) class SuggestionView: nutrient_code; display_name; text; foods
@dataclass(frozen=True) class WeekReport: ...   # exactly the skeleton's fields
def build_week(db, user, week_start, today) -> WeekReport
def suggested_codes(db, user, week_start, today) -> list[str]
```
- The HTTP contract, which Task 8 writes into `frontend/src/report/types.ts`:

| Method and path | Answer |
|---|---|
| `GET /reports/week?start=YYYY-MM-DD` | 200 `WeeklyReportOut` |
| | 422 when `start` is not a Sunday, or falls after the current week |
| | 404 "Complete your profile first" |

```
WeeklyReportOut {
  start_date, end_date, status: "complete" | "in-progress", tracked_days: int,
  slots: {logged: int, skipped: int, expected: int},
  measured_kcal: int, estimated_kcal: int,
  plan: {planned: int, followed: int} | null,
  days: [{date, weekday: "Sun".."Sat", state: "tracked"|"untracked"|"in-progress"|"future",
          energy_kcal: int, target_kcal: int}],
  nutrients: [{code, display_name, unit, category, kind, measured_days: int,
               target_total, ear_total: float | null, consumed_total,   -- one decimal
               days_met: int, days_over_limit: int, coverage}],         -- coverage: two decimals
  uncompensated: [{code, display_name, unit, amount, reason_code: "not_compensable"|"cap", reason}],
  suggestions: [{nutrient_code, display_name, text, foods: [{food_id, name}]}]
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reports_api.py`:

```python
"""The weekly report, end to end: the diary and the ledger in, one week's account out.

Dates run relative to the real today. A week is complete only once its Saturday
has ended, so LAST_WEEK -- the Sunday before this week's -- is the latest
complete week, and THIS_WEEK is in progress. A profile save records a weigh-in
dated today, which moves no target: one weigh-in is not a trend.

The fixture dish, Plain rice, carries 150 kcal, 4 g of protein and 30 mg of
calcium per 100 g and nothing else. Every other nutrient is unmeasured, so the
figures below follow from it by hand.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.diary import service as diary
from app.models.diary import MealLog
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient, PortionMeasure
from app.models.nutrient import Nutrient
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.models.weight import CalorieAdjustment
from app.nutrition_core.energy import Body, energy_target
from app.planner import service as planner_service
from app.reports import service as reports
from tests.test_tracking_api import PROFILE, meal_times_with

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
THIS_WEEK = planner_service.week_start_for(TODAY)
LAST_WEEK = THIS_WEEK - datetime.timedelta(days=7)
NEXT_WEEK = THIS_WEEK + datetime.timedelta(days=7)

# The reference man's energy target. Only the one test that says so recalibrates it.
FORMULA_KCAL = energy_target(
    Body(sex="male", age=25, weight_kg=65.0, activity="sedentary"), goal="maintain", pace=None
)
# Protein is 0.83 g/kg, with 0.66 g/kg as its EAR.
PROTEIN_RDA = 65.0 * 0.83
PROTEIN_EAR = 65.0 * 0.66

VEG = "vegetarian eggetarian fishetarian veg"

# (code, name, per-100g nutrients, diet tags)
INGREDIENTS = [
    ("test:ragi", "Ragi flour", {"energy": 320, "protein": 7, "calcium": 344}, VEG),
    ("test:curd", "Curd, cow milk", {"energy": 60, "protein": 3, "calcium": 150}, VEG),
    ("test:egg", "Egg, whole",
     {"energy": 155, "protein": 13, "calcium": 50}, "eggetarian fishetarian"),
    ("test:urad", "Urad dal",
     {"energy": 340, "protein": 25, "calcium": 150, "potassium": 900}, VEG),
]

# (code, name, slot tags, diet tag, yield, [(ingredient, raw grams)], (default measure, grams))
DISHES = [
    ("test:ragi-mudde", "Ragi mudde", "lunch dinner", "vegetarian", 2.0,
     [("test:ragi", 100)], ("1 ball", 150)),
    ("test:curd-rice", "Curd rice", "lunch dinner", "vegetarian", 1.2,
     [("test:rice", 300), ("test:curd", 200)], ("1 cup", 200)),
    ("test:egg-curry", "Egg curry", "lunch dinner", "eggetarian", 1.0,
     [("test:egg", 200)], ("1 egg", 60)),
]


@pytest.fixture
def tracker(signed_in, reference_data):
    """A signed-in client with the reference man's profile."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return signed_in


@pytest.fixture
def user(tracker, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def report_pool(db, reference_data) -> dict:
    """Three plannable dishes, and the ingredients they are made of, by code.

    Per default portion:
    - Ragi mudde (1 ball, 150 g): 258 mg calcium, 5.25 g protein.
    - Curd rice (1 cup, 200 g): 130 mg calcium, 6 g protein.
    - Egg curry (1 egg, 60 g): 30 mg calcium, 7.8 g protein. Never offered to a
      vegetarian.

    Urad dal is logged as it is. It is the only food here with potassium, at
    900 mg per 100 g.
    """
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    rows = {"test:rice": db.scalar(select(Ingredient).where(Ingredient.code == "test:rice"))}

    for code, name, values, tags in INGREDIENTS:
        ingredient = Ingredient(code=code, name=name, source="IFCT", diet_tags=tags)
        db.add(ingredient)
        db.flush()
        for nutrient_code, per_100g in values.items():
            db.add(
                IngredientNutrient(
                    ingredient_id=ingredient.id,
                    nutrient_id=nutrients[nutrient_code].id,
                    per_100g=per_100g,
                    source="IFCT",
                )
            )
        rows[code] = ingredient

    for code, name, slots, diet, yield_factor, recipe, (measure, grams) in DISHES:
        dish = Dish(
            code=code, name=name, source="authored", is_editable=True,
            slot_tags=slots, diet_tags=diet, yield_factor=yield_factor,
        )
        db.add(dish)
        db.flush()
        for ingredient_code, raw_grams in recipe:
            db.add(
                DishIngredient(
                    dish_id=dish.id, ingredient_id=rows[ingredient_code].id, grams=raw_grams
                )
            )
        db.add(
            PortionMeasure(dish_id=dish.id, measure_name=measure, grams=grams, is_default=True)
        )
        rows[code] = dish
    db.flush()
    return rows


def last_week(offset: int) -> datetime.date:
    return LAST_WEEK + datetime.timedelta(days=offset)


def report(api, start: datetime.date = LAST_WEEK) -> dict:
    response = api.get(f"/reports/week?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def log(
    api,
    food,
    on: datetime.date,
    slot: str,
    grams: float,
    *,
    kind: str = "dish",
    estimated: bool = False,
) -> None:
    created = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": slot, "food_id": str(food.id), "food_kind": kind,
            "grams": grams, "is_estimated": estimated,
        },
    )
    assert created.status_code == 201, created.text


def skip(api, on: datetime.date, slot: str) -> None:
    assert api.post("/diary/skips", json={"date": str(on), "slot": slot}).status_code == 201


def by_code(items: list[dict], key: str = "code") -> dict[str, dict]:
    return {item[key]: item for item in items}


def codes(week: dict) -> list[str]:
    return [s["nutrient_code"] for s in week["suggestions"]]


def names(suggestion: dict) -> list[str]:
    return [food["name"] for food in suggestion["foods"]]


def plan_for(db, owner: User, week_start: datetime.date, items) -> MealPlan:
    """A stored plan, written directly: the planner never plans a day already over."""
    plan = MealPlan(user_id=owner.id, week_start=week_start, seed=1)
    db.add(plan)
    db.flush()
    for day, slot, dish in items:
        db.add(
            MealPlanItem(
                plan_id=plan.id, plan_date=day, slot=slot, dish_id=dish.id, grams=200.0
            )
        )
    db.flush()
    return plan


def a_short_week(api, rice) -> None:
    """Three tracked days of too little last week, one of them eaten out.

    Sun  lunch 200 g              300 kcal  8 g protein  60 mg calcium; dinner skipped
    Mon  lunch 100 g, estimated   150 kcal  4 g          30 mg
    Wed  lunch 200 g              300 kcal  8 g          60 mg; lunch also skipped
    Fri  breakfast skipped, and nothing eaten
    """
    log(api, rice, last_week(0), "lunch", 200)
    skip(api, last_week(0), "dinner")
    log(api, rice, last_week(1), "lunch", 100, estimated=True)
    log(api, rice, last_week(3), "lunch", 200)
    skip(api, last_week(3), "lunch")
    skip(api, last_week(5), "breakfast")


# --- access ------------------------------------------------------------------------------


def test_the_report_needs_a_session(api_client):
    assert api_client.get(f"/reports/week?start={LAST_WEEK}").status_code == 401


def test_the_report_needs_a_profile(signed_in, reference_data):
    response = signed_in.get(f"/reports/week?start={LAST_WEEK}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Complete your profile first"


def test_a_report_week_starts_on_a_sunday(tracker):
    assert tracker.get(f"/reports/week?start={last_week(1)}").status_code == 422


def test_a_week_that_has_not_started_cannot_be_reported(tracker):
    assert tracker.get(f"/reports/week?start={NEXT_WEEK}").status_code == 422


# --- the week's shape ----------------------------------------------------------------------


def test_a_finished_week_runs_sunday_to_saturday(tracker):
    week = report(tracker)

    assert week["start_date"] == str(LAST_WEEK)
    assert week["end_date"] == str(last_week(6))
    assert week["status"] == "complete"
    assert [d["date"] for d in week["days"]] == [str(last_week(n)) for n in range(7)]
    assert [d["weekday"] for d in week["days"]] == [
        "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
    ]


def test_an_empty_week_is_untracked_rather_than_short(tracker):
    """A week the app was not used is silence, not seven days of eating nothing."""
    week = report(tracker)

    assert week["tracked_days"] == 0
    assert {d["state"] for d in week["days"]} == {"untracked"}
    assert week["slots"] == {"logged": 0, "skipped": 0, "expected": 35}
    assert week["nutrients"] == []
    assert week["uncompensated"] == []
    assert week["suggestions"] == []
    assert week["plan"] is None


def test_the_current_week_counts_only_the_days_that_have_ended(tracker, reference_data):
    log(tracker, reference_data, TODAY, "lunch", 200)

    week = report(tracker, THIS_WEEK)

    elapsed = (TODAY - THIS_WEEK).days
    states = [d["state"] for d in week["days"]]
    assert week["status"] == "in-progress"
    assert states[:elapsed] == ["untracked"] * elapsed
    assert states[elapsed] == "in-progress"
    assert states[elapsed + 1 :] == ["future"] * (6 - elapsed)
    # Today's lunch belongs to a day still being eaten, so it counts in nothing yet.
    assert week["tracked_days"] == 0
    assert week["measured_kcal"] == 0
    assert week["nutrients"] == []
    assert week["slots"] == {"logged": 0, "skipped": 0, "expected": 5 * elapsed}
    assert [d["energy_kcal"] for d in week["days"]] == [0] * 7
    assert [d["target_kcal"] for d in week["days"]] == [round(FORMULA_KCAL)] * 7


# --- days and meals ------------------------------------------------------------------------


def test_a_day_is_tracked_when_something_was_logged(tracker, reference_data):
    a_short_week(tracker, reference_data)

    week = report(tracker)

    # Friday held only a skip: something was said, but nothing eaten.
    assert [d["state"] for d in week["days"]] == [
        "tracked", "tracked", "untracked", "tracked", "untracked", "untracked", "untracked",
    ]
    assert week["tracked_days"] == 3


def test_every_meal_slot_of_the_week_is_accounted_for(tracker, reference_data):
    a_short_week(tracker, reference_data)

    # Five slots on each of seven days. Three lunches were logged -- Wednesday's
    # skip gives way to the food -- and two slots were skipped, Friday's on a day
    # with nothing eaten at all. The other thirty were missed.
    assert report(tracker)["slots"] == {"logged": 3, "skipped": 2, "expected": 35}


def test_a_snack_switched_off_is_not_expected(tracker, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    # Food eaten in it is still food, but a slot that is not expected is not
    # counted among the ones that are.
    log(tracker, reference_data, last_week(0), "snack1", 100)

    assert report(tracker)["slots"] == {"logged": 0, "skipped": 0, "expected": 28}


# --- energy ----------------------------------------------------------------------------------


def test_energy_eaten_out_is_kept_apart_from_measured_energy(tracker, reference_data):
    a_short_week(tracker, reference_data)

    week = report(tracker)

    # Sunday's and Wednesday's 300 kcal were weighed; Monday's 150 was estimated.
    assert week["measured_kcal"] == 600
    assert week["estimated_kcal"] == 150


def test_each_day_carries_its_energy_and_its_base_target(tracker, reference_data):
    a_short_week(tracker, reference_data)

    days = report(tracker)["days"]

    assert [d["energy_kcal"] for d in days] == [300, 150, 0, 300, 0, 0, 0]
    # The base target, before any carry. Sunday's shortfall raised Monday's
    # effective energy target, not the figure shown here.
    assert [d["target_kcal"] for d in days] == [round(FORMULA_KCAL)] * 7


def test_a_recalibration_mid_week_moves_only_the_days_from_it(tracker, user, db):
    db.add(
        CalorieAdjustment(
            user_id=user.id, effective_from=last_week(3), kind="step", offset_kcal=-210.0,
            reason="Your weight has risen about 0.5 kg a week.",
        )
    )
    db.flush()

    days = report(tracker)["days"]

    # Each day is costed at the target it had, not at the one in force now.
    assert [d["target_kcal"] for d in days[:3]] == [round(FORMULA_KCAL)] * 3
    assert [d["target_kcal"] for d in days[3:]] == [round(FORMULA_KCAL - 210)] * 4


# --- nutrients -------------------------------------------------------------------------------


def test_weekly_totals_count_only_the_days_that_measured_it(tracker, reference_data):
    a_short_week(tracker, reference_data)

    nutrients = by_code(report(tracker)["nutrients"])

    # Macros, then minerals. Potassium was never measured, so it is absent
    # rather than reported as a week of zeros.
    assert list(nutrients) == ["energy", "protein", "calcium"]
    assert nutrients["calcium"] == {
        "code": "calcium", "display_name": "Calcium", "unit": "mg",
        "category": "mineral", "kind": "target", "measured_days": 3,
        # Three days of the base target. Monday's effective target was 1,300 mg
        # after Sunday's carry, and summing that would count Sunday's shortfall
        # twice.
        "target_total": 3000.0, "ear_total": 2400.0, "consumed_total": 150.0,
        "days_met": 0, "days_over_limit": 0, "coverage": 1.0,
    }
    protein = nutrients["protein"]
    assert protein["target_total"] == pytest.approx(3 * PROTEIN_RDA, abs=0.06)
    assert protein["ear_total"] == pytest.approx(3 * PROTEIN_EAR, abs=0.06)
    assert protein["consumed_total"] == 20.0
    # Energy has no EAR at all.
    assert nutrients["energy"]["ear_total"] is None


def test_a_day_past_the_ear_is_met_and_a_day_past_the_limit_is_not(tracker, report_pool):
    curd = report_pool["test:curd"]
    log(tracker, curd, last_week(0), "lunch", 600, kind="ingredient")  # 900 mg calcium
    log(tracker, curd, last_week(1), "lunch", 1800, kind="ingredient")  # 2,700 mg

    calcium = by_code(report(tracker)["nutrients"])["calcium"]

    # 900 mg clears the 800 mg EAR. 2,700 mg is past the 2,500 mg upper limit,
    # which is never "met", however far past the target it is.
    assert calcium["days_met"] == 1
    assert calcium["days_over_limit"] == 1


# --- what could not be made up ---------------------------------------------------------------


def test_shortfalls_that_expired_are_reported_with_their_reason(tracker, reference_data):
    a_short_week(tracker, reference_data)

    gaps = by_code(report(tracker)["uncompensated"])

    # Energy expired too, and is left out on purpose: telling someone that
    # calories were "not made up" works against a weight goal.
    assert set(gaps) == {"protein", "calcium"}

    # Protein has no storage pool, so every short gram expired the day it happened.
    assert gaps["protein"]["reason_code"] == "not_compensable"
    assert gaps["protein"]["reason"] == (
        "Protein has no storage pool, so a short day is not carried forward."
    )
    assert gaps["protein"]["amount"] == pytest.approx(3 * PROTEIN_RDA - 20.0, abs=0.06)

    # A day carries at most 300 mg of calcium to each of the next two days.
    # - Sunday was 940 mg short, and 340 expired.
    # - Monday, owed 300, was 1,270 short, and 670 expired.
    # - Wednesday, owed Monday's second 300, was 1,240 short, and 640 expired.
    # Tuesday was untracked, so nothing was costed or expired there.
    assert gaps["calcium"] == {
        "code": "calcium", "display_name": "Calcium", "unit": "mg", "amount": 1650.0,
        "reason_code": "cap", "reason": "Beyond the 30% a day can carry, so it expired.",
    }


# --- suggestions -------------------------------------------------------------------------------


def test_suggestions_name_the_shortest_nutrients_first(tracker, reference_data):
    a_short_week(tracker, reference_data)

    suggestions = report(tracker)["suggestions"]

    # Calcium reached 5% of its week and protein 12%. Energy is never suggested.
    assert [s["nutrient_code"] for s in suggestions] == ["calcium", "protein"]
    # The fixture dish carries no slot tags, so there is no pool to suggest from.
    assert suggestions[0] == {
        "nutrient_code": "calcium",
        "display_name": "Calcium",
        "text": "Calcium fell short this week.",
        "foods": [],
    }


def test_suggestions_name_dishes_rich_in_the_nutrient(tracker, reference_data, report_pool):
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    # Best first, per default portion. Egg curry is never offered to a vegetarian.
    assert names(suggestions["calcium"]) == ["Ragi mudde", "Curd rice"]
    assert names(suggestions["protein"]) == ["Curd rice", "Ragi mudde"]
    first = suggestions["calcium"]["foods"][0]
    assert first["food_id"] == str(report_pool["test:ragi-mudde"].id)
    assert suggestions["calcium"]["text"].startswith("Calcium fell short this week.")


def test_suggested_dishes_follow_the_diet(tracker, reference_data, report_pool):
    tracker.put("/profile", json={**PROFILE, "diet_type": "eggetarian"})
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    # 7.8 g of protein in an egg's curry, 6 g in a cup of curd rice, 5.25 g in a ball of ragi.
    assert names(suggestions["protein"]) == ["Egg curry", "Curd rice", "Ragi mudde"]


def test_suggested_dishes_leave_out_avoided_foods(tracker, reference_data, report_pool):
    curd_rice = report_pool["test:curd-rice"]
    avoided = [{"label": "Curd rice", "food_id": str(curd_rice.id), "food_kind": "dish"}]
    tracker.put("/profile", json={**PROFILE, "avoided": avoided})
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    assert names(suggestions["calcium"]) == ["Ragi mudde"]
    assert names(suggestions["protein"]) == ["Ragi mudde"]


def test_potassium_is_never_pushed_on_a_potassium_sparing_drug(tracker, report_pool):
    """Spec manual step 7b. The drug already raises potassium, and more is unsafe."""
    urad = report_pool["test:urad"]
    for offset in range(3):
        log(tracker, urad, last_week(offset), "lunch", 100, kind="ingredient")
    # 450 of 3,000 mg calcium, 2,700 of 10,530 mg potassium, 75 of ~162 g protein.
    assert codes(report(tracker)) == ["calcium", "potassium", "protein"]

    tracker.put(
        "/profile",
        json={
            **PROFILE,
            "conditions": ["hypertension"],
            "medications": [{"name": "Losartan", "time": "08:00"}],
        },
    )

    # The report is derived on demand, so it reads the profile as it is now.
    assert codes(report(tracker)) == ["calcium", "protein"]


# --- the plan ----------------------------------------------------------------------------------


def test_plan_adherence_counts_the_slots_eaten_as_planned(
    tracker, user, db, reference_data, report_pool
):
    rice, curd_rice = reference_data, report_pool["test:curd-rice"]
    plan_for(
        db,
        user,
        LAST_WEEK,
        [
            (last_week(0), "lunch", rice),  # eaten as planned
            (last_week(0), "dinner", curd_rice),  # something else eaten
            (last_week(1), "lunch", curd_rice),  # nothing logged
        ],
    )
    log(tracker, rice, last_week(0), "lunch", 200)
    log(tracker, rice, last_week(0), "dinner", 200)

    assert report(tracker)["plan"] == {"planned": 3, "followed": 1}


def test_plan_items_on_days_not_yet_over_count_for_nothing(tracker, user, db, reference_data):
    plan_for(db, user, THIS_WEEK, [(TODAY, "lunch", reference_data)])

    # A plan exists, so the figure is there -- with nothing in it yet.
    assert report(tracker, THIS_WEEK)["plan"] == {"planned": 0, "followed": 0}


# --- privacy -----------------------------------------------------------------------------------


def test_another_users_diary_and_plan_never_appear(tracker, db, reference_data):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    for offset in range(7):
        db.add(
            MealLog(
                user_id=other.id, logged_on=last_week(offset), slot="lunch",
                dish_id=reference_data.id, grams=400.0, portion_label="400 g",
            )
        )
    plan_for(db, other, LAST_WEEK, [(last_week(0), "lunch", reference_data)])

    week = report(tracker)

    assert week["tracked_days"] == 0
    assert week["measured_kcal"] == 0
    assert week["slots"]["logged"] == 0
    assert week["nutrients"] == []
    assert week["plan"] is None


# --- the diary's shared readers ------------------------------------------------------------


def test_a_days_breakdown_agrees_with_the_diary_totals(
    tracker, user, db, reference_data, report_pool
):
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    log(tracker, reference_data, day, "snack2", 100, estimated=True)
    log(tracker, report_pool["test:urad"], day, "dinner", 50, kind="ingredient")

    breakdown = diary.day_breakdown(db, user, day)

    assert breakdown.consumed == pytest.approx(diary.consumed_on(db, user, day))
    assert breakdown.coverage == pytest.approx(diary.coverage_on(db, user, day))
    # Only the dal carries potassium: 50 g of the day's 350 g.
    assert breakdown.coverage["potassium"] == pytest.approx(50 / 350)
    assert breakdown.estimated_energy == pytest.approx(150.0)
    assert breakdown.logged_slots == frozenset({"lunch", "snack2", "dinner"})


def test_a_day_with_nothing_logged_breaks_down_to_nothing(user, db):
    assert diary.day_breakdown(db, user, last_week(2)) == diary.DayBreakdown(
        consumed={}, coverage={}, estimated_energy=0.0, logged_slots=frozenset()
    )


def test_slot_states_follow_the_diary_rules(tracker, user, db, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    skip(tracker, day, "lunch")  # food wins over a skip
    skip(tracker, day, "dinner")
    skip(tracker, day, "snack1")  # switched off and empty: left out, skipped or not

    assert list(diary.slot_states(db, user, day).items()) == [
        ("breakfast", "empty"),
        ("lunch", "logged"),
        ("snack2", "empty"),
        ("dinner", "skipped"),
    ]


def test_a_slot_switched_off_still_shows_food_eaten_in_it(tracker, user, db, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    log(tracker, reference_data, last_week(2), "snack1", 100)

    assert diary.slot_states(db, user, last_week(2))["snack1"] == "logged"


def test_the_diary_screen_shows_the_same_slot_states(tracker, user, db, reference_data):
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    skip(tracker, day, "dinner")

    screen = tracker.get(f"/diary?date={day}").json()

    assert [(s["slot"], s["state"]) for s in screen["slots"]] == list(
        diary.slot_states(db, user, day).items()
    )


# --- what the next plan is told --------------------------------------------------------------


def test_the_next_plan_hears_what_the_report_suggests(tracker, user, db, reference_data):
    a_short_week(tracker, reference_data)

    suggested = reports.suggested_codes(db, user, LAST_WEEK, TODAY)

    assert suggested == ["calcium", "protein"]
    week = reports.build_week(db, user, LAST_WEEK, TODAY)
    assert suggested == [s.nutrient_code for s in week.suggestions]


def test_two_tracked_days_are_too_few_to_steer_the_next_plan(tracker, user, db, reference_data):
    log(tracker, reference_data, last_week(0), "lunch", 200)
    log(tracker, reference_data, last_week(1), "lunch", 200)

    assert reports.suggested_codes(db, user, LAST_WEEK, TODAY) == []


def test_a_week_not_yet_started_suggests_nothing(user, db):
    assert reports.suggested_codes(db, user, NEXT_WEEK, TODAY) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_reports_api.py -q`
Expected: FAIL at collection, with `ImportError: cannot import name 'service' from 'app.reports'`. Task 4 created the package, but not the service.

- [ ] **Step 3: Give the diary its two shared readers**

In `app/diary/service.py`:

1. Add three imports:
   - `from dataclasses import dataclass`, after `import uuid`;
   - `from app.meal_slots import SLOTS`, after the `app.foods.nutrition` import;
   - `from app.models.profile import MealSlotTime`, after the `app.models.nutrient` import.

2. In `coverage_on`, replace its closing lines:

```python
    if total_grams <= 0:
        return {}

    return {code: min(grams / total_grams, 1.0) for code, grams in covered.items()}
```

   with:

```python
    return _shares(covered, total_grams)
```

   Then add this helper directly below `coverage_on`:

```python
def _shares(covered: dict[str, float], total_grams: float) -> dict[str, float]:
    """Covered grams per code, as a share of the day's food weight."""
    if total_grams <= 0:
        return {}
    return {code: min(grams / total_grams, 1.0) for code, grams in covered.items()}
```

3. Below `consumed_on`, add:

```python
@dataclass(frozen=True)
class DayBreakdown:
    """One day of the diary, added up in a single pass over its entries.

    The weekly report needs a day's totals, its coverage and its estimated share.
    Through `consumed_on` and `coverage_on` that is a pass each, and every pass
    costs each dish again.
    """

    consumed: dict[str, float]  # == consumed_on(day)
    coverage: dict[str, float]  # == coverage_on(day)
    # Energy from entries marked estimated -- eaten out, or eyeballed -- which the
    # report keeps apart from measured intake.
    estimated_energy: float
    logged_slots: frozenset[str]


def day_breakdown(db: Session, user: User, on_date: datetime.date) -> DayBreakdown:
    totals: dict[str, float] = {}
    covered: dict[str, float] = {}
    total_grams = 0.0
    estimated = 0.0
    slots: set[str] = set()

    for entry in list_entries(db, user, on_date):
        slots.add(entry.slot)
        nutrients = entry_nutrients(db, entry)
        for code, amount in nutrients.items():
            totals[code] = totals.get(code, 0.0) + amount
        if entry.is_estimated:
            estimated += nutrients.get("energy", 0.0)

        total_grams += entry.grams
        for code, share in entry_coverage(db, entry).items():
            covered[code] = covered.get(code, 0.0) + share * entry.grams

    return DayBreakdown(
        consumed=totals,
        coverage=_shares(covered, total_grams),
        estimated_energy=estimated,
        logged_slots=frozenset(slots),
    )
```

4. Below `skipped_on`, add `slot_states`. It carries the rules `read_diary` applied inline, and their comments move with them:

```python
def slot_states(db: Session, user: User, on_date: datetime.date) -> dict[str, str]:
    """Each slot's state on a date, in `SLOTS` order: logged, skipped or empty.

    `skipped` is not `empty`. Empty means the app does not know what happened in
    the slot; skipped means the user said nothing was eaten there. The diary
    screen, the weekly report and the reminders all read this, so the rules live
    here once.

    Reads slot names only, not entries, because the reminder runner calls it
    every minute for each subscribed user with a slot due.
    """
    logged = set(
        db.scalars(
            select(MealLog.slot)
            .where(MealLog.user_id == user.id, MealLog.logged_on == on_date)
            .distinct()
        )
    )
    skipped = skipped_on(db, user, on_date)
    # A profile with no saved meal times at all predates onboarding's meal-times
    # step, so every slot is shown rather than none.
    disabled = set(
        db.scalars(
            select(MealSlotTime.slot).where(
                MealSlotTime.user_id == user.id, MealSlotTime.is_enabled.is_(False)
            )
        )
    )

    states: dict[str, str] = {}
    for slot in SLOTS:
        if slot in logged:
            # Food wins over a skip: having eaten is a stronger fact than having
            # said you would not.
            states[slot] = "logged"
        elif slot in disabled:
            # A slot switched off is left out -- but only when the day has nothing
            # in it. Turning a snack off says how a normal day looks from now on;
            # it is not a claim about last week, and hiding a real entry would be
            # rewriting what the user actually ate.
            continue
        elif slot in skipped:
            states[slot] = "skipped"
        else:
            states[slot] = "empty"
    return states
```

- [ ] **Step 4: Make `read_diary` read the slot states**

In `app/diary/router.py`, replace the whole `read_diary` function, from `@router.get("", response_model=DiaryOut)` down to and including `return DiaryOut(date=date, slots=slots)`, with:

```python
@router.get("", response_model=DiaryOut)
def read_diary(
    date: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiaryOut:
    entries = service.list_entries(db, user, date)
    meal_times = profiles.get_meal_times(db, user)
    times = {item.slot: item.usual_time.strftime("%H:%M") for item in meal_times}

    # Which slots appear, and in which state, is `slot_states`' call: the report
    # and the reminders read the same rules this screen shows.
    return DiaryOut(
        date=date,
        slots=[
            SlotOut(
                slot=slot,
                time=times.get(slot, DEFAULT_SLOT_TIMES[slot]),
                state=state,
                entries=[
                    EntryOut(
                        id=entry.id,
                        name=service.entry_name(db, entry),
                        portion=entry.portion_label,
                        measure_name=entry.measure_name,
                        quantity=entry.quantity,
                        grams=entry.grams,
                        is_estimated=entry.is_estimated,
                        energy_kcal=service.entry_nutrients(db, entry).get("energy", 0.0),
                    )
                    for entry in entries
                    if entry.slot == slot
                ],
            )
            for slot, state in service.slot_states(db, user, date).items()
        ],
    )
```

The output is unchanged. `SLOTS` stays imported, because `create_entry` and the skip routes still validate against it.

- [ ] **Step 5: Write the report service**

Create `app/reports/service.py`:

```python
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
```

- [ ] **Step 6: Write the router, and include it**

Create `app/reports/router.py`:

```python
"""The weekly report over HTTP."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.local_time import local_today
from app.models.user import User
from app.planner import rules
from app.planner import service as planner
from app.reports import service, summary

router = APIRouter(prefix="/reports", tags=["reports"])


class SlotsOut(BaseModel):
    logged: int
    skipped: int
    # The slots enabled now, on every day that has ended. Whatever is neither
    # logged nor skipped was missed.
    expected: int


class PlanAdherenceOut(BaseModel):
    planned: int
    followed: int


class ReportDayOut(BaseModel):
    date: datetime.date
    weekday: str
    state: str  # tracked | untracked | in-progress | future
    energy_kcal: int
    target_kcal: int


class NutrientWeekOut(BaseModel):
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    measured_days: int
    target_total: float
    ear_total: float | None
    consumed_total: float
    days_met: int
    days_over_limit: int
    coverage: float


class GapOut(BaseModel):
    code: str
    display_name: str
    unit: str
    amount: float
    reason_code: str  # not_compensable | cap
    reason: str


class SuggestedFoodOut(BaseModel):
    food_id: uuid.UUID
    name: str


class SuggestionOut(BaseModel):
    nutrient_code: str
    display_name: str
    text: str
    foods: list[SuggestedFoodOut]


class WeeklyReportOut(BaseModel):
    start_date: datetime.date
    end_date: datetime.date
    status: str  # complete | in-progress
    tracked_days: int
    slots: SlotsOut
    measured_kcal: int
    estimated_kcal: int
    plan: PlanAdherenceOut | None
    days: list[ReportDayOut]
    nutrients: list[NutrientWeekOut]
    uncompensated: list[GapOut]
    suggestions: list[SuggestionOut]


def _amount(value: float) -> float:
    return round(value, 1)


def _nutrient_out(week: summary.NutrientWeek) -> NutrientWeekOut:
    return NutrientWeekOut(
        code=week.code,
        display_name=week.display_name,
        unit=week.unit,
        category=week.category,
        kind=week.kind,
        measured_days=week.measured_days,
        target_total=_amount(week.target_total),
        ear_total=_amount(week.ear_total) if week.ear_total is not None else None,
        consumed_total=_amount(week.consumed_total),
        days_met=week.days_met,
        days_over_limit=week.days_over_limit,
        coverage=round(week.coverage, 2),
    )


def _out(report: service.WeekReport) -> WeeklyReportOut:
    plan = None
    if report.plan_planned is not None and report.plan_followed is not None:
        plan = PlanAdherenceOut(planned=report.plan_planned, followed=report.plan_followed)
    return WeeklyReportOut(
        start_date=report.start_date,
        end_date=report.end_date,
        status=report.status,
        tracked_days=report.tracked_days,
        slots=SlotsOut(
            logged=report.slots_logged,
            skipped=report.slots_skipped,
            expected=report.slots_expected,
        ),
        measured_kcal=round(report.measured_kcal),
        estimated_kcal=round(report.estimated_kcal),
        plan=plan,
        days=[
            ReportDayOut(
                date=day.date,
                weekday=day.weekday,
                state=day.state,
                energy_kcal=round(day.energy_kcal),
                target_kcal=round(day.target_kcal),
            )
            for day in report.days
        ],
        nutrients=[_nutrient_out(week) for week in report.nutrients],
        uncompensated=[
            GapOut(
                code=gap.code,
                display_name=gap.display_name,
                unit=gap.unit,
                amount=_amount(gap.amount),
                reason_code=gap.reason_code,
                reason=gap.reason,
            )
            for gap in report.uncompensated
        ],
        suggestions=[
            SuggestionOut(
                nutrient_code=item.nutrient_code,
                display_name=item.display_name,
                text=item.text,
                foods=[
                    SuggestedFoodOut(food_id=food_id, name=name)
                    for food_id, name in item.foods
                ],
            )
            for item in report.suggestions
        ],
    )


@router.get("/week", response_model=WeeklyReportOut)
def read_week(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeeklyReportOut:
    """One week's report, derived from the diary on every request and never stored."""
    if rules.sunday_index(start) != 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A report week starts on a Sunday"
        )
    today = local_today(user)
    if start > planner.week_start_for(today):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That week has not started yet")
    try:
        report = service.build_week(db, user, start, today)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    return _out(report)
```

The route only reads, so it does not commit.

In `app/main.py`:
- add `from app.reports.router import router as reports_router` after the `app.profiles.router` import;
- add `app.include_router(reports_router)` after the last `app.include_router(...)` line.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_reports_api.py tests/test_tracking_api.py -q && uv run ruff check .`
Expected: all PASS, and ruff is clean. The tracking suite's diary tests pass unchanged, which is the check that `read_diary` answers exactly as before.

- [ ] **Step 8: Commit**

```bash
git add app/reports/service.py app/reports/router.py app/diary/service.py \
  app/diary/router.py app/main.py tests/test_reports_api.py
git commit -m "feat(backend): add the weekly report service and GET /reports/week

The report is derived on demand and never stored, so nothing can go stale. It
takes one ledger walk from four days before the Sunday, and one pass over
each tracked day's diary. It counts tracked days and meal slots, and keeps
energy eaten out apart from measured energy. It totals each nutrient over
the days that measured it, so a gap in the food tables never reads as a
deficit, and lists the shortfalls that expired with the reason they could
not be made up.

It suggests at most three nutrients, with dishes from the planner's own
pool. A suggestion therefore respects diet and avoided foods, and never
pushes potassium on a potassium-sparing drug. suggested_codes gives the
next week's plan the same nutrients, without the dish lookup.

The diary gains day_breakdown, one pass for totals, coverage and the
estimated share. It also gains slot_states, which now holds the rules for
logged, skipped and empty that read_diary applied inline, so the report
and the reminders count the same states the diary screen shows.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Suggestions feed the next plan

The spec's report step ends with "next week's suggested foods, feeding into the next plan". Task 5 works out which nutrients a week fell short on. This task makes the following week's plan lean on them. The planner already scores every dish by a weighted nutrient gap, so leaning is a matter of weight: each suggested nutrient's shortfall costs `EMPHASIS_FACTOR` (1.5×) more, and a close choice between two dishes tips toward the one that carries it. The emphasis is stored on the plan when the plan is made. A swap and an off-plan re-plan therefore lean the same way all week, and a regenerate reads last week again. Nothing here is a hard constraint, so an emphasis can never admit a dish the rules refuse.

**Files:**
- Modify:
  - `app/planner/engine.py`: `EMPHASIS_FACTOR`, `NutrientGoal.weight`, and `weighted_gap` reading it
  - `app/planner/service.py`: `emphasised`, `plan_emphasis`, `_last_weeks_emphasis`, `_never_emphasised`, `DayContext.never_emphasised`, `_day_input(..., emphasis=)`, `generate_week`, `replan_after_log`, `swap_item`
- Test: `tests/test_planner_engine.py` (append), `tests/test_planner_api.py` (append)

**Interfaces:**
- Consumes:
  - Task 3: `MealPlan.emphasis` (`String(200)`, `''` by default).
  - Task 5: `app.reports.service.suggested_codes(db, user, week_start, today) -> list[str]`. It returns worst first, and `[]` when that week had fewer than 3 tracked days.
- Produces:
```python
# app/planner/engine.py
EMPHASIS_FACTOR = 1.5
@dataclass(frozen=True)
class NutrientGoal:
    code: str; display_name: str; amount: float; kind: str
    tul: float | None = None
    weight: float | None = None   # None -> NUTRIENT_WEIGHTS.get(code, DEFAULT_WEIGHT)
# weighted_gap uses goal.weight when set, for target-kind goals only.

# app/planner/service.py
def emphasised(goals: dict[str, NutrientGoal], emphasis: frozenset[str]) -> dict[str, NutrientGoal]
    # weight = NUTRIENT_WEIGHTS.get(code, DEFAULT_WEIGHT) * EMPHASIS_FACTOR for each target-kind
    # goal whose code is in `emphasis`; every other goal unchanged; idempotent
def plan_emphasis(plan: MealPlan) -> frozenset[str]   # frozenset(plan.emphasis.split())
# MealPlan.emphasis: the codes suggested_codes returned for the week before, space-separated,
# worst first; set when generate_week creates the plan and on reseed, never on a swap or re-plan.
```
- The report module is imported lazily inside `_last_weeks_emphasis`, because `app.reports.service` imports `app.planner.service` at module level for `load_pool` and `get_plan` (Task 5 builds its avoided `FoodRef`s itself rather than calling the private `_food_refs`). That direction may stay a module-level import. `app.planner.service` must never import `app.reports` at module level.

- [ ] **Step 1: Write the failing tests**

In `tests/test_planner_engine.py`, add `from dataclasses import replace` after `import uuid`, and add `EMPHASIS_FACTOR,` as the first name in the `from app.planner.engine import (...)` list. Ruff's isort puts constants before classes. Then append:

```python


# --- emphasis: what last week's report found short -------------------------------------


def test_an_emphasised_target_weighs_its_shortfall_more():
    plain = {"calcium": GOALS["calcium"]}
    # Calcium's usual weight is 1.5; emphasised, it is 1.5 x 1.5.
    stressed = {"calcium": replace(GOALS["calcium"], weight=1.5 * EMPHASIS_FACTOR)}

    # Half the goal is a relative shortfall of 0.5.
    assert weighted_gap({"calcium": 500.0}, plain) == pytest.approx(0.75)
    assert weighted_gap({"calcium": 500.0}, stressed) == pytest.approx(1.125)
    # An emphasis costs nothing once the goal is met.
    assert weighted_gap({"calcium": 1000.0}, stressed) == 0.0


def test_a_weight_leaves_a_ceiling_alone():
    heavy = {"sodium": replace(GOALS["sodium"], weight=9.0)}

    # 3,000 mg is 50% over the 2,000 mg ceiling, costed at CEILING_WEIGHT's 2.0.
    assert weighted_gap({"sodium": 3000.0}, heavy) == pytest.approx(1.0)


# Two lunches a close call apart: pesarattu carries the protein, ragi mudde the
# calcium. One portion each, so the only thing being chosen is the dish.
PESARATTU = candidate(
    "Pesarattu", {"lunch"}, energy=400, protein=20, calcium=60, grams=(100.0,)
)
RAGI_MUDDE = candidate(
    "Ragi mudde", {"lunch"}, energy=400, protein=5, calcium=340, grams=(100.0,)
)


def test_an_emphasis_tips_a_close_choice_toward_its_nutrient():
    lunch = {"lunch": (PESARATTU, RAGI_MUDDE)}
    stressed = {**GOALS, "calcium": replace(GOALS["calcium"], weight=1.5 * EMPHASIS_FACTOR)}

    # At the usual weights pesarattu's extra 15 g of protein is worth 0.50 and
    # ragi mudde's extra 280 mg of calcium 0.42, so pesarattu wins by 0.08. At
    # calcium's emphasised 2.25 the calcium is worth 0.63: ragi mudde, by 0.13.
    usual = plan_day(day(slots=lunch), rng())
    leaning = plan_day(day(slots=lunch, goals=stressed), rng())

    assert [item.dish_id for item in usual] == [PESARATTU.dish_id]
    assert [item.dish_id for item in leaning] == [RAGI_MUDDE.dish_id]
```

These figures are the whole day's cost against `GOALS`, with one 100 g portion in the day's only slot:
- Pesarattu costs 6.1433 unweighted and 6.8483 with calcium emphasised.
- Ragi mudde costs 6.2233 and 6.7183.

With one slot and two candidates, the local search always ends on the cheaper dish, so the seeded jitter cannot change either answer.

In `tests/test_planner_api.py`, add `from app.planner import engine` on the line before `from app.planner import service as planner`, and append:

```python


# --- last week's report leans this week's plan ------------------------------------------------


def this_and_last_week() -> tuple[datetime.date, datetime.date]:
    """This week's Sunday, and the Sunday before it: a week that has ended."""
    this_week = planner.week_start_for(datetime.datetime.now(KOLKATA).date())
    return this_week, this_week - datetime.timedelta(days=7)


def log_rice_lunches(api, rice: Dish, week_start: datetime.date, days: int) -> None:
    """200 g of plain rice for lunch from the Monday on: 60 mg of calcium a day, of 1,000."""
    for offset in range(1, days + 1):
        log(api, rice, week_start + datetime.timedelta(days=offset), "lunch")


def first_arguments(monkeypatch, name: str) -> list:
    """Spy on `engine.<name>`, recording the first argument of every call to it."""
    seen: list = []
    original = getattr(engine, name)

    def spy(first, *args, **kwargs):
        seen.append(first)
        return original(first, *args, **kwargs)

    monkeypatch.setattr(engine, name, spy)
    return seen


def test_an_emphasis_raises_only_the_named_targets_weight():
    goals = {
        "calcium": engine.NutrientGoal("calcium", "Calcium", 1000.0, "target"),
        "iron": engine.NutrientGoal("iron", "Iron", 19.0, "target"),
        "sodium": engine.NutrientGoal("sodium", "Sodium", 2000.0, "ceiling"),
    }

    leaning = planner.emphasised(goals, frozenset({"calcium", "sodium", "vitamin_d"}))

    assert leaning["calcium"].weight == pytest.approx(2.25)  # calcium's 1.5, times 1.5
    assert leaning["calcium"].amount == 1000.0
    assert leaning["iron"] == goals["iron"]
    # A ceiling has no shortfall to weigh, and a code with no goal adds none.
    assert leaning["sodium"] == goals["sodium"]
    assert set(leaning) == set(goals)


def test_applying_an_emphasis_twice_changes_nothing():
    goals = {"calcium": engine.NutrientGoal("calcium", "Calcium", 1000.0, "target")}

    once = planner.emphasised(goals, frozenset({"calcium"}))

    assert planner.emphasised(once, frozenset({"calcium"})) == once


def test_a_plans_emphasis_reads_back_as_a_set():
    assert planner.plan_emphasis(MealPlan(emphasis="calcium protein")) == {"calcium", "protein"}
    assert planner.plan_emphasis(MealPlan(emphasis="")) == frozenset()
    # A row not yet flushed has no column default applied.
    assert planner.plan_emphasis(MealPlan()) == frozenset()


def test_a_week_short_on_calcium_emphasises_it_next_week(
    signed_in, planner_pool, reference_data, db, monkeypatch
):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    this_week, last_week = this_and_last_week()
    # Four tracked days, each at 6% of the calcium goal.
    log_rice_lunches(signed_in, reference_data, last_week, days=4)
    planned = first_arguments(monkeypatch, "plan_week")

    week(signed_in, this_week)

    assert "calcium" in planner.get_plan(db, _user(db), this_week).emphasis.split()
    # Every day the plan covers leans on it, not only the first.
    days = planned[0]
    assert days
    assert all(day.goals["calcium"].weight == pytest.approx(2.25) for day in days)


def test_a_thinly_logged_week_leaves_the_next_plan_unemphasised(
    signed_in, planner_pool, reference_data, db
):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    this_week, last_week = this_and_last_week()
    # Two tracked days are too few to call anything a pattern.
    log_rice_lunches(signed_in, reference_data, last_week, days=2)

    week(signed_in, this_week)

    assert planner.get_plan(db, _user(db), this_week).emphasis == ""


def test_the_emphasis_stands_until_the_week_is_regenerated(
    signed_in, planner_pool, reference_data, db
):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    this_week, last_week = this_and_last_week()
    week(signed_in, this_week)

    # Last week is filled in after the plan was made. The stored plan stands...
    log_rice_lunches(signed_in, reference_data, last_week, days=4)
    week(signed_in, this_week)
    assert planner.get_plan(db, _user(db), this_week).emphasis == ""

    # ...until a regenerate reads last week again.
    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(this_week)})
    assert regenerated.status_code == 200, regenerated.text
    assert "calcium" in planner.get_plan(db, _user(db), this_week).emphasis.split()


def test_a_swap_plans_with_the_stored_emphasis(signed_in, planner_pool, db, monkeypatch):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")
    planner.get_plan(db, _user(db), WEEK).emphasis = "calcium"
    db.flush()
    swapped_with = first_arguments(monkeypatch, "alternative_for")

    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 200

    assert swapped_with[0].goals["calcium"].weight == pytest.approx(2.25)
    assert swapped_with[0].goals["protein"].weight is None


def test_an_off_plan_log_replans_with_the_stored_emphasis(
    signed_in, planner_pool, db, monkeypatch
):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    planned_lunch = item_in(week(signed_in), MONDAY, "lunch")
    planner.get_plan(db, _user(db), WEEK).emphasis = "calcium"
    db.flush()
    replanned_with = first_arguments(monkeypatch, "plan_day")
    off_plan = next(
        d for d in planner_pool.values()
        if str(d.id) != planned_lunch["dish_id"] and "lunch" in d.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")

    assert len(replanned_with) == 1
    assert replanned_with[0].goals["calcium"].weight == pytest.approx(2.25)


def test_a_stored_emphasis_never_pushes_potassium_on_ramipril(
    signed_in, planner_pool, db, monkeypatch
):
    """Spec manual step 7b, for a drug started mid-week.

    The report stops suggesting potassium the moment ramipril is on the profile,
    but this week's plan was made before that and keeps its emphasis until it
    is regenerated. The swap must not lean on potassium in the meantime.
    """
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")
    planner.get_plan(db, _user(db), WEEK).emphasis = "potassium calcium"
    db.flush()
    signed_in.put(
        "/profile",
        json={**NON_VEG_PROFILE, "medications": [{"name": "Ramipril", "time": "08:00"}]},
    )
    swapped_with = first_arguments(monkeypatch, "alternative_for")

    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 200

    goals = swapped_with[0].goals
    assert goals["potassium"].weight is None
    assert goals["calcium"].weight == pytest.approx(2.25)
```

The report's arithmetic behind the calcium tests:
- Each day's 200 g of the fixture's plain rice (`test:rice`, 30 mg of calcium per 100 g) is 60 mg of calcium against a 1,000 mg base target, measured at full coverage.
- Four days make a `consumed_total` of 240 mg against a `target_total` of 4,000 mg. That is 6% of the target, well under the 90% line, on 4 measured days out of 4 tracked, which clears the minimum of 3.
- Protein, at 32 g of about 216 g, is suggested too.
- The rice carries no other nutrient, so nothing else is measured.
- Two days fall under the 3-tracked-day minimum, so `suggested_codes` returns `[]`.

`this_week` is the current week's Sunday, so the week before it has ended by the time any test runs. The four Monday-to-Thursday lunches are always in the past. Their diary posts re-plan nothing, because last week has no plan. The spy tests fix `emphasis` by hand on the upcoming week's plan, so they test the stored emphasis being applied rather than the report.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_planner_engine.py -q`
Expected: collection ERROR: `ImportError: cannot import name 'EMPHASIS_FACTOR' from 'app.planner.engine'`

Run: `uv run pytest tests/test_planner_api.py -q -k emphasis`
Expected: 8 failed, 1 passed. `-k emphasis` selects exactly the nine new tests.
- `test_an_emphasis_raises_only_the_named_targets_weight` and `test_applying_an_emphasis_twice_changes_nothing` fail with `AttributeError: module 'app.planner.service' has no attribute 'emphasised'`.
- `test_a_plans_emphasis_reads_back_as_a_set` fails with the same error for `'plan_emphasis'`.
- The swap, re-plan and ramipril tests fail with `AttributeError: 'NutrientGoal' object has no attribute 'weight'`.
- `test_a_week_short_on_calcium_emphasises_it_next_week` and the regenerate test fail on `assert 'calcium' in []`.
- `test_a_thinly_logged_week_leaves_the_next_plan_unemphasised` already passes, because Task 3's column defaults to `''`. It stays as the guard on the 3-day minimum.

- [ ] **Step 3: Give a goal its own weight**

In `app/planner/engine.py`:

1. Below `DEFAULT_WEIGHT = 1.0`, add:

```python
# A nutrient last week's report found short weighs this much more in the next
# week's plan. Enough to tip a close choice toward the dish that carries it; not
# so much that any emphasised nutrient outweighs energy, which sizes the day.
EMPHASIS_FACTOR = 1.5
```

Protein's 2.0 × 1.5 reaches energy's 3.0 and does not pass it. Calcium, iron and fibre go to 2.25, and anything unlisted goes to 1.5.

2. In `NutrientGoal`, below `tul: float | None = None`, add:

```python
    # The weight on a target's relative shortfall. None is the planner's usual
    # figure from NUTRIENT_WEIGHTS; a week's emphasis sets it higher. A ceiling's
    # overshoot always weighs CEILING_WEIGHT, so this is never read for one.
    weight: float | None = None
```

It is the last field, and it has a default, so every positional `NutrientGoal(code, name, amount, kind, tul)` keeps working. That covers `build_context` and the engine tests' `GOALS`.

3. Add above `weighted_gap`:

```python
def _shortfall_weight(goal: NutrientGoal) -> float:
    """What falling short of a target costs, per unit of relative shortfall."""
    if goal.weight is not None:
        return goal.weight
    return NUTRIENT_WEIGHTS.get(goal.code, DEFAULT_WEIGHT)
```

4. In `weighted_gap`, replace the two lines of the `else:` branch

```python
            weight = NUTRIENT_WEIGHTS.get(goal.code, DEFAULT_WEIGHT)
            gap += weight * max(0.0, 1.0 - have / goal.amount)
```

with

```python
            gap += _shortfall_weight(goal) * max(0.0, 1.0 - have / goal.amount)
```

- [ ] **Step 4: Store the emphasis on the plan, and plan with it**

In `app/planner/service.py`:

1. Replace the two imports

```python
from app.models.profile import AvoidedFood, FavouriteIngredient, MealSlotTime, Profile
```
```python
from app.nutrition_core.conditions import EMPTY_STOMACH_DRUGS
```

with

```python
from app.models.profile import AvoidedFood, FavouriteIngredient, MealSlotTime, Medication, Profile
```
```python
from app.nutrition_core.conditions import EMPTY_STOMACH_DRUGS, POTASSIUM_SPARING_DRUGS
```

2. In `DayContext`, below `consumed: dict[str, float] = field(default_factory=dict)`, add:

```python
    # What a stored emphasis may not push on this day: see `_never_emphasised`.
    never_emphasised: frozenset[str] = frozenset()
```

3. In `build_context`, replace

```python
    doses = [
        item.taken_at
        for item in profiles.get_medications(db, user)
        if any(name in item.name.lower() for name in EMPTY_STOMACH_DRUGS)
    ]
```

with

```python
    medications = profiles.get_medications(db, user)
    doses = [
        item.taken_at
        for item in medications
        if any(name in item.name.lower() for name in EMPTY_STOMACH_DRUGS)
    ]
```

and, in its `return DayContext(...)`, add after `consumed=diary.consumed_on(db, user, day),`:

```python
        never_emphasised=_never_emphasised(resolved.hold_steady, medications),
```

4. Add this section between `build_context` and `# --- stored plans ---`:

```python
# --- last week's report, this week's emphasis ---------------------------------------------


def emphasised(
    goals: dict[str, NutrientGoal], emphasis: frozenset[str]
) -> dict[str, NutrientGoal]:
    """The goals, with each emphasised target's shortfall weighed EMPHASIS_FACTOR more.

    The weight is the planner's usual one times the factor -- never the goal's
    current weight times it -- so applying an emphasis twice changes nothing.
    """
    weighted = dict(goals)
    for code in emphasis:
        goal = goals.get(code)
        if goal is not None and goal.kind == "target":
            usual = engine.NUTRIENT_WEIGHTS.get(code, engine.DEFAULT_WEIGHT)
            weighted[code] = replace(goal, weight=usual * engine.EMPHASIS_FACTOR)
    return weighted


def plan_emphasis(plan: MealPlan) -> frozenset[str]:
    """The nutrient codes a stored plan leans on; empty when it leans on none."""
    return frozenset((plan.emphasis or "").split())


def _last_weeks_emphasis(db: Session, user: User, week_start: datetime.date) -> str:
    """What `MealPlan.emphasis` stores for a week: the codes last week's report suggests.

    Read when a plan is made and when it is regenerated, never on a swap or a
    re-plan, so a week's plan leans the same way from Sunday to Saturday.
    """
    # Imported here to avoid a cycle: the report service reads this module's pool.
    from app.reports import service as reports

    previous = week_start - datetime.timedelta(days=WEEK_DAYS)
    today = local_today(user)
    if previous >= today:
        # Planning ahead: the week before this one has no finished day yet.
        return ""
    return " ".join(reports.suggested_codes(db, user, previous, today))


def _never_emphasised(
    hold_steady: frozenset[str], medications: Sequence[Medication]
) -> frozenset[str]:
    """What no emphasis may push, whatever last week's report said.

    The report leaves these out already, but a plan's emphasis is fixed for its
    week: someone who starts warfarin or ramipril on a Wednesday must not have
    Thursday's re-plan lean on vitamin K or potassium.
    """
    unsafe = set(hold_steady)
    if any(
        name in item.name.lower() for item in medications for name in POTASSIUM_SPARING_DRUGS
    ):
        unsafe.add("potassium")
    return frozenset(unsafe)
```

5. In `_day_input`, replace

```python
    favourites: tuple[FoodRef, ...],
) -> DayInput:
    return DayInput(
        date=context.date,
        goals=context.goals,
```

with

```python
    favourites: tuple[FoodRef, ...],
    *,
    emphasis: frozenset[str],
) -> DayInput:
    return DayInput(
        date=context.date,
        goals=emphasised(context.goals, emphasis - context.never_emphasised),
```

The argument is keyword-only and required, so a caller cannot forget it. `context.goals` itself stays unweighted: `build_context`'s callers and tests read amounts from it, and a weight is a planning concern only.

6. In `generate_week`, add two lines to the end of the docstring, after "...so the plan covers the remainder.":

```python
    Every day leans on what last week's report found short, read afresh when
    the plan is made or regenerated and stored on it.
```

Then replace

```python
    plan = get_plan(db, user, week_start)
    if plan is None:
        plan = MealPlan(user_id=user.id, week_start=week_start, seed=_new_seed())
        db.add(plan)
        db.flush()
    elif reseed:
        plan.seed = _new_seed()
        db.flush()
```

with

```python
    plan = get_plan(db, user, week_start)
    if plan is None:
        plan = MealPlan(
            user_id=user.id,
            week_start=week_start,
            seed=_new_seed(),
            emphasis=_last_weeks_emphasis(db, user, week_start),
        )
        db.add(plan)
        db.flush()
    elif reseed:
        plan.seed = _new_seed()
        # Last week's diary may have been filled in since the plan was made.
        plan.emphasis = _last_weeks_emphasis(db, user, week_start)
        db.flush()
    emphasis = plan_emphasis(plan)
```

and replace

```python
        inputs.append(_day_input(context, pool, open_slots, fixed, favourites))
```

with

```python
        inputs.append(
            _day_input(context, pool, open_slots, fixed, favourites, emphasis=emphasis)
        )
```

7. In `replan_after_log`, replace

```python
    day_input = _day_input(context, pool, open_slots, fixed, favourites)
```

with

```python
    day_input = _day_input(
        context, pool, open_slots, fixed, favourites, emphasis=plan_emphasis(plan)
    )
```

8. In `swap_item`, replace

```python
        _food_refs(db, user, FavouriteIngredient),
    )
```

with

```python
        _food_refs(db, user, FavouriteIngredient), emphasis=plan_emphasis(plan),
    )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_planner_engine.py tests/test_planner_api.py tests/test_reports_api.py -q && uv run ruff check .`
Expected: all PASS, and ruff is clean.

The existing planner tests pass unchanged, for two reasons:
- Every goal they build has no weight, so `weighted_gap` reads `NUTRIENT_WEIGHTS` exactly as before.
- Every plan they generate gets an empty emphasis. The upcoming week's previous week is the current one, with nothing logged before generation. The current week's previous week is empty too.

The report tests run too, because every first request for a week now builds the report of the week before it.

- [ ] **Step 6: Commit**

```bash
git add app/planner/engine.py app/planner/service.py \
  tests/test_planner_engine.py tests/test_planner_api.py
git commit -m "feat(backend): lean the next week's plan on what the last report found short

The weekly report's suggestions now feed the plan, as the spec's report step
asks. When a week's plan is made, each nutrient the previous week's report
suggests weighs 1.5x in the planner's gap. That is at most three, and never
energy, anything held steady, or potassium on a drug that raises it. A close
choice between dishes then tips toward the one that carries the nutrient. A
thin week, with fewer than three tracked days, leans on nothing.

The emphasis is stored on the plan, so a swap and an off-plan re-plan lean
the same way all week. A regenerate re-reads last week, since its diary may
have been filled in since. A drug started mid-week takes its nutrient out of
the stored emphasis at once, rather than at the next regenerate.

NutrientGoal gains an optional trailing weight, so every positional
construction keeps working. The report service is imported lazily, because
it reads the planner's pool.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Household weekly progress, as counts

The spec shares daily and weekly progress by default, so whoever cooks can see how everyone's week went; this plan builds the weekly counts (daily is a recorded gap). It never shares health data. A target counts as health data, because a 1,500 mg sodium cap reveals hypertension. So each member's week reaches the household as three counts: days logged, nutrient-days on track, and nutrient-days measured. Nothing names a nutrient or a figure, whatever `share_health` says. The counts are the member's own weekly report summed over the targets a profile has before any condition overlay, which depend only on sex and age band. A condition can add a target nobody else has: high cholesterol adds a cholesterol ceiling, and from 60, when the reference rows carry no sodium or potassium, hypertension adds both (potassium only without a potassium-sparing drug). An added target would put one more nutrient-day on every logged day, and a household eating the same food would read the diagnosis off the difference. A condition that only moves a figure (sodium to 1,500 mg) changes which days are met, never how many are counted; the Decisions accept that. A member who has turned `share_progress` off is still listed, with no figures. The caller always sees their own counts.

**Files:**
- Modify:
  - `app/reports/service.py`: `ProgressCounts`, `member_progress`
  - `app/households/router.py`: the `GET /households/progress` route
- Test: `tests/test_household_progress_api.py` (create)

**Interfaces:**
- Consumes:
  - Task 5: `reports.service.build_week`, and on the `WeekReport` it returns, `tracked_days` and `nutrients` (each `NutrientWeek`'s `days_met` and `measured_days`); `GET /reports/week`, in the tests only
  - Task 2: `targets.load_context`, and `TargetContext.built` (the targets before the condition overlay)
  - `households.service.get_membership` and `list_members`; `app.local_time.local_today`; `planner.rules.sunday_index`; `profiles.service.get_profile`
- Produces:
```python
# app/reports/service.py
@dataclass(frozen=True)
class ProgressCounts:
    tracked_days: int; nutrient_days_met: int; nutrient_days_measured: int
def member_progress(db: Session, member: User, week_start: datetime.date,
                    today: datetime.date) -> ProgressCounts | None   # None: member has no profile
```
- Also produces the HTTP contract that Task 13 reads:

| Method and path | Answer |
|---|---|
| `GET /households/progress?start=YYYY-MM-DD` | 200 `HouseholdProgressOut`; 401 signed out; 404 not in a household; 422 when `start` is not a Sunday or the week has not begun |

```
HouseholdProgressOut {
  start_date
  members: [{user_id, name, is_me, shared: bool,        # you first, then in the order they joined
             tracked_days: int | null,
             nutrient_days_met: int | null,
             nutrient_days_measured: int | null}]       # null when not shared, or no profile
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_household_progress_api.py`:

```python
"""What a household sees of each member's week: counts of days on track, never targets.

Weekly progress is shared by default, so whoever cooks can see how the week went.
A target is health data -- a 1,500 mg sodium cap says hypertension, 8 mg of iron
says menopause -- so the household gets counts of days and nothing that names a
nutrient or a figure.

Last week is the one week certain to be over. Dates run from the real today,
because every profile save records a weigh-in dated today.

The fixture dish is 150 kcal, 4 g of protein and 30 mg of calcium per 100 g, and
measures nothing else, so a day of it measures exactly three nutrients. 1,600 g
is 2,400 kcal and 64 g of protein -- over the reference man's 2,105 kcal and his
42.9 g protein EAR -- but only 480 mg of calcium, under its 800 mg EAR: two of the
three are met. 50 g meets none of them. The two condition tests give it one more
figure each, so that a target only a condition sets has something to measure.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.auth import google as google_auth
from app.models.food import DishIngredient, IngredientNutrient
from app.models.nutrient import Nutrient
from app.planner import service as planner_service
from tests.conftest import NUTRIENTS
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
THIS_WEEK = planner_service.week_start_for(TODAY)
LAST_WEEK = THIS_WEEK - datetime.timedelta(days=7)

TWO_OF_THREE_GRAMS = 1600
NONE_OF_THREE_GRAMS = 50

# (sub, email, name). The tracker is the `signed_in` fixture's account.
TRACKER = ("sub-track", "track@example.com", "Tracker")
RAVI = ("sub-ravi", "ravi@example.com", "Ravi")

COUNT_KEYS = ("tracked_days", "nutrient_days_met", "nutrient_days_measured")
MEMBER_KEYS = {"user_id", "name", "is_me", "shared", *COUNT_KEYS}


def day(n: int) -> datetime.date:
    """Day n of last week; 0 is its Sunday."""
    return LAST_WEEK + datetime.timedelta(days=n)


def sign_in_as(api, monkeypatch, person: tuple[str, str, str]) -> None:
    """Switch the client to another Google account, as another phone would be."""
    sub, email, name = person
    identity = {"sub": sub, "email": email, "email_verified": True, "name": name}
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: identity,
    )
    api.post("/auth/logout")
    assert api.post("/auth/google", json={"credential": "t"}).status_code == 200


def eat(api, dish, on: datetime.date, grams: float) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": grams, "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


def add_ravi(api, monkeypatch, dish, *, profile=PROFILE, meals=(), share_progress=True):
    """Invite Ravi. He joins, onboards unless `profile` is None, and logs `meals`
    ((date, grams) of the fixture dish); then the client is the tracker's again."""
    token = api.post("/households/invites", json={"email": RAVI[1]}).json()["token"]
    sign_in_as(api, monkeypatch, RAVI)
    assert api.post("/households/invites/accept", json={"token": token}).status_code == 200
    if profile is not None:
        assert api.put("/profile", json=profile).status_code == 200
    for on, grams in meals:
        eat(api, dish, on, grams)
    if not share_progress:
        response = api.patch("/households/visibility", json={"share_progress": False})
        assert response.status_code == 200
    sign_in_as(api, monkeypatch, TRACKER)


def progress(api, start: datetime.date = LAST_WEEK) -> dict:
    response = api.get(f"/households/progress?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, name: str) -> dict:
    return next(item for item in body["members"] if item["name"] == name)


def counts(item: dict) -> tuple:
    return tuple(item[key] for key in COUNT_KEYS)


def add_to_the_rice(db, dish, nutrient: Nutrient, per_100g: float) -> None:
    """Give the fixture dish's one ingredient a figure for `nutrient`."""
    rice = db.scalars(
        select(DishIngredient.ingredient_id).where(DishIngredient.dish_id == dish.id)
    ).one()
    db.add(
        IngredientNutrient(
            ingredient_id=rice, nutrient_id=nutrient.id, per_100g=per_100g, source="IFCT"
        )
    )
    db.flush()


@pytest.fixture
def api(signed_in, reference_data):
    """The tracker, onboarded, in a household of one."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    assert signed_in.post("/households", json={"name": "Home"}).status_code == 201
    return signed_in


def test_progress_needs_a_session(api_client):
    assert api_client.get(f"/households/progress?start={LAST_WEEK}").status_code == 401


def test_progress_needs_a_household(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    response = signed_in.get(f"/households/progress?start={LAST_WEEK}")

    assert response.status_code == 404
    assert response.json()["detail"] == "You are not in a household yet"


def test_the_week_starts_on_a_sunday(api):
    response = api.get(f"/households/progress?start={day(1)}")

    assert response.status_code == 422
    assert response.json()["detail"] == "The week starts on a Sunday"


def test_a_week_not_yet_begun_is_refused(api):
    next_week = THIS_WEEK + datetime.timedelta(days=7)
    assert api.get(f"/households/progress?start={next_week}").status_code == 422


def test_you_see_your_own_week_as_counts(api, reference_data):
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    eat(api, reference_data, day(3), NONE_OF_THREE_GRAMS)
    me = api.get("/auth/me").json()["id"]

    assert progress(api) == {
        "start_date": str(LAST_WEEK),
        "members": [
            {
                "user_id": me,
                "name": "Tracker",
                "is_me": True,
                "shared": True,
                # Two days logged with three nutrients measured on each: six
                # nutrient-days, of which Sunday's energy and protein were on track.
                "tracked_days": 2,
                "nutrient_days_met": 2,
                "nutrient_days_measured": 6,
            }
        ],
    }


def test_the_counts_are_your_own_report_summed(api, reference_data):
    """One set of figures: with no condition adding a target, the household reads
    exactly the sums of the member's own report."""
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    eat(api, reference_data, day(3), NONE_OF_THREE_GRAMS)

    mine = row(progress(api), "Tracker")
    report = api.get(f"/reports/week?start={LAST_WEEK}").json()

    assert mine["tracked_days"] == report["tracked_days"]
    assert mine["nutrient_days_met"] == sum(n["days_met"] for n in report["nutrients"])
    assert mine["nutrient_days_measured"] == sum(
        n["measured_days"] for n in report["nutrients"]
    )


def test_a_member_sharing_progress_appears_with_counts(api, reference_data, monkeypatch):
    add_ravi(api, monkeypatch, reference_data, meals=[(day(1), TWO_OF_THREE_GRAMS)])

    body = progress(api)

    # You first, then the others.
    assert [item["name"] for item in body["members"]] == ["Tracker", "Ravi"]
    ravi = row(body, "Ravi")
    assert ravi["is_me"] is False
    assert ravi["shared"] is True
    assert counts(ravi) == (1, 2, 3)


def test_a_member_not_sharing_is_listed_without_figures(api, reference_data, monkeypatch):
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        meals=[(day(1), TWO_OF_THREE_GRAMS)],
        share_progress=False,
    )

    ravi = row(progress(api), "Ravi")

    assert ravi["shared"] is False
    assert counts(ravi) == (None, None, None)


def test_not_sharing_hides_you_from_the_household_but_not_from_yourself(
    api, reference_data, monkeypatch
):
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(api, monkeypatch, reference_data)
    assert api.patch("/households/visibility", json={"share_progress": False}).status_code == 200

    mine = row(progress(api), "Tracker")
    assert mine["shared"] is True
    assert counts(mine) == (1, 2, 3)

    sign_in_as(api, monkeypatch, RAVI)
    body = progress(api)
    assert body["members"][0]["name"] == "Ravi"
    assert body["members"][0]["is_me"] is True
    # A week with nothing logged is zero days, not unknown.
    assert counts(body["members"][0]) == (0, 0, 0)
    tracker = row(body, "Tracker")
    assert tracker["shared"] is False
    assert counts(tracker) == (None, None, None)


def test_a_member_without_a_profile_has_no_figures(api, reference_data, monkeypatch):
    add_ravi(api, monkeypatch, reference_data, profile=None)

    ravi = row(progress(api), "Ravi")

    assert ravi["shared"] is True
    assert counts(ravi) == (None, None, None)


def test_nothing_names_a_nutrient_or_a_target(api, reference_data, monkeypatch):
    """Both have hypertension, whose 1,500 mg sodium cap would say so on its own."""
    hypertensive = {**PROFILE, "conditions": ["hypertension"]}
    assert api.put("/profile", json=hypertensive).status_code == 200
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        profile=hypertensive,
        meals=[(day(2), TWO_OF_THREE_GRAMS)],
    )

    response = api.get(f"/households/progress?start={LAST_WEEK}")
    body = response.json()

    assert set(body) == {"start_date", "members"}
    for item in body["members"]:
        assert set(item) == MEMBER_KEYS
        # Small whole numbers of days, with no room left for a figure like 1,500 mg.
        assert counts(item) == (1, 2, 3)
    text = response.text.lower()
    for code, display_name, *_ in NUTRIENTS:
        assert code not in text
        assert display_name.lower() not in text
    assert "kcal" not in text
    assert "mg" not in text


def test_a_target_only_a_condition_sets_adds_no_nutrient_days(api, reference_data, db):
    """High cholesterol sets a cholesterol ceiling that no other profile has. Counted,
    it would add a nutrient-day to every logged day, and a household eating the same
    food would read the diagnosis off the difference."""
    cholesterol = Nutrient(
        code="cholesterol",
        display_name="Cholesterol",
        unit="mg",
        category="macro",
        is_compensable=False,
        compensation_days=0,
        is_excess_sensitive=True,
    )
    db.add(cholesterol)
    db.flush()
    # IFCT gives every food a cholesterol figure, zero for plants, and a zero still measures.
    add_to_the_rice(db, reference_data, cholesterol, 0.0)
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    assert counts(row(progress(api), "Tracker")) == (1, 2, 3)

    profile = {**PROFILE, "conditions": ["high_cholesterol"]}
    assert api.put("/profile", json=profile).status_code == 200

    # The member's own report carries the ceiling, measured and met...
    report = api.get(f"/reports/week?start={LAST_WEEK}").json()
    assert "cholesterol" in {n["code"] for n in report["nutrients"]}
    # ...and the household's counts are what they were without the condition.
    assert counts(row(progress(api), "Tracker")) == (1, 2, 3)


def test_hypertension_from_sixty_adds_no_nutrient_days(api, reference_data, db, monkeypatch):
    """From 60 the reference rows carry no potassium, so hypertension adds a potassium
    target nobody else of that age has. Counted, it would add a nutrient-day to every
    logged day and say who has high blood pressure."""
    potassium = db.scalars(select(Nutrient).where(Nutrient.code == "potassium")).one()
    add_to_the_rice(db, reference_data, potassium, 100.0)
    elder = {**PROFILE, "age": 65}
    assert api.put("/profile", json=elder).status_code == 200
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        profile={**elder, "conditions": ["hypertension"]},
        meals=[(day(0), TWO_OF_THREE_GRAMS)],
    )

    body = progress(api)

    # Without the filter Ravi's potassium, measured and short, reads one more.
    assert counts(row(body, "Ravi")) == counts(row(body, "Tracker"))


def test_the_day_in_progress_is_not_counted(api, reference_data):
    """Today's lunch is part of a day, not a day. It counts once the day is over."""
    eat(api, reference_data, TODAY, TWO_OF_THREE_GRAMS)

    mine = row(progress(api, start=THIS_WEEK), "Tracker")

    assert counts(mine) == (0, 0, 0)
```

Where the expected counts come from, all on the migrated fixture data with no carry reaching a counted day:

| Day of the dish | Energy (target 2,105.3 kcal, no EAR) | Protein (EAR 42.9 g) | Calcium (EAR 800 mg) | Met of measured |
|---|---|---|---|---|
| 1,600 g | 2,400 kcal: met | 64 g: met | 480 mg: not met | 2 of 3 |
| 50 g | 75 kcal: not met | 2 g: not met | 15 mg: not met | 0 of 3 |

- No carry reaches a counted day, which matters for energy. Energy has no EAR, so it is judged against its effective target, and an incoming shortfall carry could raise that by up to 30%, to about 2,737 kcal, above 2,400.
  - Each scenario's first logged day starts clean: the walk starts four days before Sunday, and nothing is logged there.
  - Carries land one and two days on, so Sunday's reach Monday and Tuesday. The only second logged day in any test is the tracker's small Wednesday, three days on.
- Protein and calcium are judged against their EARs, which no carry moves.
- None of the nutrients comes near an upper limit: calcium's is 2,500 mg.

The two condition tests pin the filter in `member_progress`:
- With high cholesterol, the rice's zero cholesterol is measured and under the 200 mg ceiling, so an unfiltered sum reads (1, 3, 4).
- At 65 the test database has no reference rows at all, so both members' targets are the computed macros, and calcium is not one of them. Ravi's hypertension adds sodium and potassium; the rice carries no sodium, but its potassium is measured, so an unfiltered sum gives Ravi one more nutrient-day than the tracker.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_household_progress_api.py -q`
Expected: FAIL, 14 failed. There is no `/households/progress` route yet, so every request to it answers 404 `{"detail": "Not Found"}`. `test_progress_needs_a_household` fails too, on its detail assertion.

- [ ] **Step 3: Count a member's week**

Append the following to `app/reports/service.py`. Task 5's module already imports everything this uses: `datetime`, `dataclass`, `Session`, `User`, `from app.profiles import service as profiles`, and `from app.targets import service as targets`.

```python
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
```

- [ ] **Step 4: The route**

In `app/households/router.py`:

1. Replace the first three import lines:
   ```python
   import uuid

   from fastapi import APIRouter, Depends, HTTPException, status
   ```
   with:
   ```python
   import datetime
   import uuid

   from fastapi import APIRouter, Depends, HTTPException, Query, status
   ```

2. Add `from app.local_time import local_today` after `from app.households import service`. Then add these two lines after `from app.models.user import User`:
   ```python
   from app.planner import rules
   from app.reports import service as reports
   ```

3. Add the response models after `MembershipOut`:

```python
class MemberProgressOut(BaseModel):
    user_id: uuid.UUID
    name: str
    is_me: bool
    # Whether this viewer may see the member's counts; always true on your own row.
    shared: bool
    # Counts of days, never a nutrient or a figure. Null when the member does not
    # share progress, or has not set up a profile yet.
    tracked_days: int | None
    nutrient_days_met: int | None
    nutrient_days_measured: int | None


class HouseholdProgressOut(BaseModel):
    start_date: datetime.date
    members: list[MemberProgressOut]
```

4. Add this helper below `_to_household_out`:

```python
def _member_progress_out(
    member: User, is_me: bool, shared: bool, counts: reports.ProgressCounts | None
) -> MemberProgressOut:
    return MemberProgressOut(
        user_id=member.id,
        name=member.name,
        is_me=is_me,
        shared=shared,
        tracked_days=counts.tracked_days if counts is not None else None,
        nutrient_days_met=counts.nutrient_days_met if counts is not None else None,
        nutrient_days_measured=counts.nutrient_days_measured if counts is not None else None,
    )
```

5. Append the route at the end of the file:

```python
@router.get("/progress", response_model=HouseholdProgressOut)
def read_progress(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdProgressOut:
    """Each member's week as counts of days on track, so whoever cooks can see it.

    Counts only, whatever `share_health` says: a target is health data -- a
    1,500 mg sodium cap says hypertension -- so no nutrient and no figure leaves
    the member it belongs to.
    """
    if rules.sunday_index(start) != 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The week starts on a Sunday")
    if start > local_today(user):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That week has not started yet")
    membership = service.get_membership(db, user)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")

    # You first, then everyone else in the order they joined.
    rows = sorted(
        service.list_members(db, membership.household_id),
        key=lambda item: item.user_id != user.id,
    )
    members = []
    for row in rows:
        member = db.get(User, row.user_id)
        is_me = row.user_id == user.id
        shared = is_me or row.share_progress
        counts = None
        if shared:
            # The member's own today: a day still in progress where they are is
            # not a finished day, wherever the viewer is.
            counts = reports.member_progress(db, member, start, local_today(member))
        members.append(_member_progress_out(member, is_me, shared, counts))
    return HouseholdProgressOut(start_date=start, members=members)
```

- On a Sunday, `start > local_today(user)` holds exactly when the week begins after the current one, so no week arithmetic is needed.
- The route writes nothing, so it does not commit.
- Importing `app.reports.service` here makes no cycle. `main.py` imports this router first, and by the time the reports service loads the planner service (which imports `app.households.service`), that module is already fully loaded.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_household_progress_api.py tests/test_household_api.py tests/test_reports_api.py -q && uv run ruff check .`
Expected: all PASS, and ruff is clean. `test_household_api.py` is unchanged, since the existing routes are untouched. `test_reports_api.py` still passes, because `member_progress` only adds to the module.

- [ ] **Step 6: Commit**

```bash
git add app/reports/service.py app/households/router.py tests/test_household_progress_api.py
git commit -m "feat(backend): show the household each member's week, as counts only

GET /households/progress?start= lists the caller first, then the other members
in the order they joined. Each row gives days logged, and nutrient-days on
track out of nutrient-days measured. It does so for the caller and for every
member who shares progress, which is the default. A member who has turned
sharing off is still listed, with no figures.

Nothing in it names a nutrient or a target, whatever share_health says. A
target is health data: a 1,500 mg sodium cap reveals hypertension, and 8 mg
of iron reveals menopause.

The counts are the member's own weekly report summed over the targets every
profile has before any condition. A target only a condition creates, such as
high cholesterol's cholesterol ceiling or, from 60, hypertension's potassium,
would add a nutrient-day to every logged day and give the diagnosis away.
Each member's week runs to their own today, so a day still in progress
counts nowhere.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Frontend — the Report screen on the real endpoint

This task moves the Report screen off its MSW fixture and onto Task 5's endpoint. Today the screen asks for the week in progress and shows a proposal-era shape: `days_met` out of a fixed 7, weekly limits made by multiplying a daily TUL by seven, and suggestions as free prose. It now opens on the last complete week, steps back and forward a week at a time, and shows the figures the backend derives. The energy chart draws each day against its own target, so a mid-week recalibration moves the line from that day on. A day with nothing logged is drawn as an outline rather than a zero bar, so a day of silence never looks like a day of eating nothing. The Report stays lazy-loaded, so `App.tsx` does not change.

All paths are relative to `frontend/`, and every command runs from there.

**Files:**
- Modify:
  - `src/report/types.ts`: the Task 5 contract
  - `src/report/ReportScreen.tsx`
  - `src/report/EnergyChart.tsx`: a per-day target, distinct untracked days, and a labelled table
  - `src/report/ReportScreen.test.tsx`: stubs the endpoint per test
  - `src/mocks/fixtures/report.ts`
  - `src/mocks/handlers/index.ts`: the report handler is deleted
- Create: `src/report/useReport.ts`

**Interfaces:**
- Consumes:
  - Task 5's `GET /reports/week?start=YYYY-MM-DD`, which answers 200 `WeeklyReportOut`, 422 for a start that is not a Sunday or falls after the current week, and 404 "Complete your profile first".
  - Existing code: `weekStartIso` (`src/plan/usePlan.ts`), `formatDay` (plan 7, `src/lib/format.ts`), `nutrientStatus`, `STATUS_LABELS` / `STATUS_TEXT`, `Badge`, `Button`, `EmptyState` and `Skeleton`.
- Produces:
```ts
// src/report/useReport.ts
export function useWeeklyReport(start: string)   // query key ['reports', 'week', start]
export function lastCompleteWeekStart(from?: Date): string   // the Sunday before this week's
export function addDays(iso: string, days: number): string   // calendar days, timezone-safe

// src/report/types.ts: WeeklyReport and its parts, exactly Task 5's WeeklyReportOut
// src/mocks/fixtures/report.ts: REPORT_FIXTURE (16-22 Aug 2026, complete) and
//   IN_PROGRESS_REPORT_FIXTURE (23-29 Aug 2026, opened on Wednesday the 26th)
```
- Task 14's e2e walk can rely on these names:
  - the week range is an `h2` reading `16 Aug 2026 – 22 Aug 2026`, with an en dash;
  - the buttons are named "Previous week" and "Next week";
  - a week still going shows the text "In progress";
  - the first figure is labelled "Days logged";
  - the table behind the chart is named "Energy each day against that day’s target".

- [ ] **Step 1: Write the contract as built**

Replace `src/report/types.ts`:

```ts
import type { NutrientUnit } from '../lib/format'
import type { NutrientKind } from '../lib/status'

/**
 * CONTRACT for `GET /reports/week?start=` — plan 8.
 *
 * `start` must be a Sunday no later than the current week's, or the answer is a
 * 422. A missing profile is a 404. The report is derived on every request and
 * never stored.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec:
 * - a week still going has its own status;
 * - each day says whether it was tracked;
 * - every total counts only the days that measured it;
 * - meals are logged, skipped or missed, and a stored plan's adherence is given;
 * - an expired shortfall carries a reason code as well as words;
 * - a suggestion names the dishes it proposes.
 */

/** `complete` once the Saturday has ended where the user is. */
export type ReportStatus = 'complete' | 'in-progress'

/**
 * - `tracked`: over, with something logged. Only these count in any total.
 * - `untracked`: over, with nothing logged. Silence, not a day of eating nothing.
 * - `in-progress`: today. It counts once it is over.
 * - `future`: still to come.
 */
export type DayState = 'tracked' | 'untracked' | 'in-progress' | 'future'

export interface ReportDay {
  date: string
  /** "Sun" to "Sat". */
  weekday: string
  state: DayState
  /** Whole kcal. 0 on every day that is not tracked. */
  energy_kcal: number
  /** That day's own energy target before any carry, at the recalibration then in force. */
  target_kcal: number
}

export interface SlotCounts {
  logged: number
  /** "Nothing eaten here": accounted for, not missed. */
  skipped: number
  /** The slots enabled now, on every day that has ended. The rest were missed. */
  expected: number
}

export interface PlanAdherence {
  /** Planned meals on the days that have ended. */
  planned: number
  /** Of those, the slots logged with the planned dish. */
  followed: number
}

export interface ReportNutrient {
  code: string
  display_name: string
  unit: NutrientUnit
  category: 'macro' | 'mineral' | 'vitamin'
  kind: NutrientKind
  /** Tracked days on which something logged carried a figure for it. */
  measured_days: number
  /**
   * Each measured day's base target, before carries, summed. Summing the
   * effective targets would count a made-up shortfall twice.
   */
  target_total: number
  /** The EAR over the same days, summed. Null where there is no EAR. */
  ear_total: number | null
  consumed_total: number
  /** Measured days in Today's "on target" band. */
  days_met: number
  /** Measured days at or past the daily upper limit. No weekly sum is set against it. */
  days_over_limit: number
  /** Mean share of each measured day's food weight that carried a figure for it, 0 to 1. */
  coverage: number
}

/**
 * A shortfall the ledger could not make up, summed over the week. The spec
 * requires the report to show these rather than quietly drop them. Energy never
 * appears here, and neither does anything held steady.
 */
export interface UncompensatedGap {
  code: string
  display_name: string
  unit: NutrientUnit
  amount: number
  /** `not_compensable`: never carried, as protein. `cap`: beyond what a day may carry. */
  reason_code: 'not_compensable' | 'cap'
  reason: string
}

export interface SuggestedFood {
  food_id: string
  name: string
}

/**
 * A nutrient that fell short, with dishes from the plan's own pool that carry it.
 * The next week's plan weighs these nutrients more.
 */
export interface Suggestion {
  nutrient_code: string
  display_name: string
  text: string
  foods: SuggestedFood[]
}

export interface WeeklyReport {
  start_date: string
  end_date: string
  status: ReportStatus
  tracked_days: number
  slots: SlotCounts
  /** Energy from entries not marked estimated, over tracked days. */
  measured_kcal: number
  /** Energy from entries marked estimated: eaten out, or eyeballed. */
  estimated_kcal: number
  /** Null when the week has no stored plan. */
  plan: PlanAdherence | null
  days: ReportDay[]
  /** Macros, then minerals, then vitamins, each by name. */
  nutrients: ReportNutrient[]
  uncompensated: UncompensatedGap[]
  /** At most three, worst first. */
  suggestions: Suggestion[]
}
```

Replace `src/mocks/fixtures/report.ts`:

```ts
import type { DayState, ReportDay, WeeklyReport } from '../../report/types'

function day(
  date: string,
  weekday: string,
  state: DayState,
  energy_kcal: number,
  target_kcal: number,
): ReportDay {
  return { date, weekday, state, energy_kcal, target_kcal }
}

/**
 * A week that went partly wrong, which is the only kind worth designing for.
 *
 * - Nothing was logged on Tuesday.
 * - A weigh-in on Thursday stepped the energy target down 210 kcal from that day on.
 * - Calcium and fibre fell short, and part of each expired past the carry cap.
 * - Protein was short on days it can never carry.
 * - Sodium ran over its ceiling.
 * - A quarter of the week's energy was estimated.
 *
 * The figures follow the backend's rounding: kcal whole, amounts to one decimal,
 * coverage to two.
 */
export const REPORT_FIXTURE: WeeklyReport = {
  start_date: '2026-08-16',
  end_date: '2026-08-22',
  status: 'complete',
  tracked_days: 6,
  slots: { logged: 26, skipped: 3, expected: 35 },
  measured_kcal: 9160,
  estimated_kcal: 2980,
  plan: { planned: 28, followed: 17 },
  days: [
    day('2026-08-16', 'Sun', 'tracked', 2240, 2105),
    day('2026-08-17', 'Mon', 'tracked', 1420, 2105),
    day('2026-08-18', 'Tue', 'untracked', 0, 2105),
    day('2026-08-19', 'Wed', 'tracked', 1960, 2105),
    day('2026-08-20', 'Thu', 'tracked', 2310, 1895),
    day('2026-08-21', 'Fri', 'tracked', 1870, 1895),
    day('2026-08-22', 'Sat', 'tracked', 2340, 1895),
  ],
  nutrients: [
    {
      code: 'fibre',
      display_name: 'Dietary fibre',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 5,
      target_total: 151.6,
      ear_total: null,
      consumed_total: 118.4,
      days_met: 1,
      days_over_limit: 0,
      coverage: 0.86,
    },
    {
      code: 'energy',
      display_name: 'Energy',
      unit: 'kcal',
      category: 'macro',
      kind: 'target',
      measured_days: 6,
      target_total: 12002.0,
      ear_total: null,
      consumed_total: 12140.0,
      days_met: 3,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 6,
      target_total: 323.7,
      ear_total: 257.4,
      consumed_total: 296.4,
      days_met: 3,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 6,
      target_total: 6000.0,
      ear_total: 4800.0,
      consumed_total: 3710.0,
      days_met: 1,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'iron',
      display_name: 'Iron',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 6,
      target_total: 114.0,
      ear_total: 66.0,
      consumed_total: 105.2,
      days_met: 4,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'sodium',
      display_name: 'Sodium',
      unit: 'mg',
      category: 'mineral',
      kind: 'ceiling',
      measured_days: 6,
      target_total: 12000.0,
      ear_total: null,
      consumed_total: 14820.0,
      days_met: 2,
      days_over_limit: 0,
      coverage: 0.91,
    },
    {
      code: 'vitamin_b12',
      display_name: 'Vitamin B12',
      unit: 'ug',
      category: 'vitamin',
      kind: 'target',
      measured_days: 6,
      target_total: 15.0,
      ear_total: 12.0,
      consumed_total: 21.8,
      days_met: 5,
      days_over_limit: 0,
      coverage: 0.62,
    },
  ],
  uncompensated: [
    {
      code: 'fibre',
      display_name: 'Dietary fibre',
      unit: 'g',
      amount: 22.6,
      reason_code: 'cap',
      reason: 'Beyond the 25% a day can carry, so it expired.',
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      amount: 57.0,
      reason_code: 'not_compensable',
      reason: 'Protein has no storage pool, so a short day is not carried forward.',
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      amount: 1240.0,
      reason_code: 'cap',
      reason: 'Beyond the 30% a day can carry, so it expired.',
    },
  ],
  suggestions: [
    {
      nutrient_code: 'calcium',
      display_name: 'Calcium',
      text:
        'Calcium fell short this week. ' +
        'Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam.',
      foods: [
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a01', name: 'Ragi mudde' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a02', name: 'Curd rice' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a03', name: 'Moong dal payasam' },
      ],
    },
    {
      nutrient_code: 'fibre',
      display_name: 'Dietary fibre',
      text: 'Dietary fibre fell short this week. Dishes that carry it: Sundal, Keerai kootu.',
      foods: [
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a04', name: 'Sundal' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a05', name: 'Keerai kootu' },
      ],
    },
  ],
}

/**
 * The week after, opened on its Wednesday. Sunday and Monday were logged and
 * Tuesday was not. Today and the rest of the week still count for nothing.
 * Two tracked days are too few for a suggestion.
 */
export const IN_PROGRESS_REPORT_FIXTURE: WeeklyReport = {
  start_date: '2026-08-23',
  end_date: '2026-08-29',
  status: 'in-progress',
  tracked_days: 2,
  slots: { logged: 8, skipped: 1, expected: 15 },
  measured_kcal: 3790,
  estimated_kcal: 400,
  plan: { planned: 12, followed: 7 },
  days: [
    day('2026-08-23', 'Sun', 'tracked', 1980, 1895),
    day('2026-08-24', 'Mon', 'tracked', 2210, 1895),
    day('2026-08-25', 'Tue', 'untracked', 0, 1895),
    day('2026-08-26', 'Wed', 'in-progress', 0, 1895),
    day('2026-08-27', 'Thu', 'future', 0, 1895),
    day('2026-08-28', 'Fri', 'future', 0, 1895),
    day('2026-08-29', 'Sat', 'future', 0, 1895),
  ],
  nutrients: [
    {
      code: 'energy',
      display_name: 'Energy',
      unit: 'kcal',
      category: 'macro',
      kind: 'target',
      measured_days: 2,
      target_total: 3790.7,
      ear_total: null,
      consumed_total: 4190.0,
      days_met: 2,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 2,
      target_total: 107.9,
      ear_total: 85.8,
      consumed_total: 110.2,
      days_met: 2,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 2,
      target_total: 2000.0,
      ear_total: 1600.0,
      consumed_total: 1410.0,
      days_met: 1,
      days_over_limit: 0,
      coverage: 1.0,
    },
  ],
  uncompensated: [],
  suggestions: [],
}
```

The complete week's figures agree with each other:
- **Energy.** The tracked days add up to 12,140 kcal, which is 9,160 measured plus 2,980 estimated. 2,980 is 24.5% of that, which the screen rounds to 25%.
- **Energy target.** 12,002 kcal is three days at 2,105.34 and three at 1,895.34.
- **Protein.** 323.7 g is 6 × 53.95 and 257.4 g is 6 × 42.9. 296.4 g is between the two, so the week reads "on target".
- **Fibre.** 151.6 g is three days at 31.58 g plus two at 28.43 g, the fibre target following each day's energy.
- **Suggestions.** Calcium (62%) and fibre (78%) are under 90% of their totals and are suggested, worst first. Protein (92%) and iron (92%) are not.

Replace `src/mocks/handlers/index.ts`:

```ts
import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'
import { apiUrl } from '../apiUrl'
import { REMINDERS_FIXTURE } from '../fixtures/more'
import { demoAuthHandlers } from './demoAuth'

/**
 * Handlers for endpoints the backend has NOT built yet.
 *
 * Nothing here shadows a real endpoint. Auth, households, food search, the whole
 * tracking loop — profile, targets and diary — the meal planner, weight, cycle
 * and the weekly report exist in FastAPI, so requests to them fall through to the
 * real server in dev (`onUnhandledRequest: 'bypass'`) and are stubbed per-test
 * in Vitest.
 *
 * These handlers are the proposed HTTP contract for the plans still outstanding.
 * When a plan implements one, delete its handler and its screen's
 * `DemoDataBanner`.
 */
export const handlers: RequestHandler[] = [
  // Opt-in only, so the default set never shadows a real endpoint.
  ...(import.meta.env.VITE_DEMO_AUTH === 'true' ? demoAuthHandlers : []),

  // Plan 8 — per-slot reminder scheduling. The meal *times* themselves are saved
  // with the profile and are real; toggling reminders is not wired up yet.
  http.get(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
  http.patch(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
]
```

- [ ] **Step 2: Write the failing tests**

Replace `src/report/ReportScreen.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { IN_PROGRESS_REPORT_FIXTURE, REPORT_FIXTURE } from '../mocks/fixtures/report'
import { server } from '../mocks/server'
import { ReportScreen } from './ReportScreen'
import type { WeeklyReport } from './types'
import { addDays, lastCompleteWeekStart } from './useReport'

/*
 * Wednesday 26 August 2026. This week began on Sunday the 23rd, so the last
 * complete week, the one the screen opens on, is 16 to 22 August: the fixture's
 * week. Only `Date` is faked, so React Query, MSW and user-event keep their real
 * timers.
 */
const NOW = new Date(2026, 7, 26, 10, 0)

let requested: string[] = []

function stubReport(report: WeeklyReport) {
  server.use(http.get(apiUrl('/reports/week'), () => HttpResponse.json(report)))
}

function stubStatus(status: number) {
  server.use(http.get(apiUrl('/reports/week'), () => new HttpResponse('error', { status })))
}

beforeEach(() => {
  requested = []
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  server.use(
    http.get(apiUrl('/reports/week'), ({ request }) => {
      const start = new URL(request.url).searchParams.get('start') ?? ''
      requested.push(start)
      const inProgress = start === IN_PROGRESS_REPORT_FIXTURE.start_date
      return HttpResponse.json(inProgress ? IN_PROGRESS_REPORT_FIXTURE : REPORT_FIXTURE)
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReportScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** The fixture week has loaded: its meals figure is on screen. */
async function loaded() {
  await screen.findByText('29 of 35')
}

/** A row of the nutrients table. */
function nutrientRow(name: string) {
  return within(screen.getByRole('rowheader', { name }).closest('tr')!)
}

/** A row of the table behind the energy chart. */
async function dayRow(weekday: string) {
  const table = await screen.findByRole('table', { name: /energy each day/i })
  return within(within(table).getByRole('rowheader', { name: weekday }).closest('tr')!)
}

// --- which week ----------------------------------------------------------------------

test('the last complete week is the one before this week', () => {
  // Thursday 24 September 2026. This week began on Sunday the 20th.
  expect(lastCompleteWeekStart(new Date(2026, 8, 24, 9, 0))).toBe('2026-09-13')
})

test('on a Sunday, the week just ended is the last complete one', () => {
  expect(lastCompleteWeekStart(new Date(2026, 8, 20, 9, 0))).toBe('2026-09-13')
})

test('late on a Saturday, the week is not complete yet', () => {
  expect(lastCompleteWeekStart(new Date(2026, 8, 19, 23, 30))).toBe('2026-09-06')
})

test('weeks are counted across a month and across a year', () => {
  expect(lastCompleteWeekStart(new Date(2026, 7, 3, 9, 0))).toBe('2026-07-26')
  expect(addDays('2026-12-27', 7)).toBe('2027-01-03')
})

test('opens on the last complete week, from the real endpoint', async () => {
  renderScreen()

  await loaded()
  expect(requested).toEqual(['2026-08-16'])
  expect(screen.getByRole('heading', { name: '16 Aug 2026 – 22 Aug 2026' })).toBeInTheDocument()
  expect(screen.queryByText('In progress')).not.toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

test('Previous week asks for the week before', async () => {
  renderScreen()
  await loaded()

  await userEvent.click(screen.getByRole('button', { name: 'Previous week' }))

  expect(
    await screen.findByRole('heading', { name: '9 Aug 2026 – 15 Aug 2026' }),
  ).toBeInTheDocument()
  await waitFor(() => expect(requested).toEqual(['2026-08-16', '2026-08-09']))
})

test('Next week goes as far as the week in progress, and no further', async () => {
  renderScreen()
  await loaded()
  expect(screen.getByRole('button', { name: 'Next week' })).toBeEnabled()

  await userEvent.click(screen.getByRole('button', { name: 'Next week' }))

  expect(await screen.findByText('In progress')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '23 Aug 2026 – 29 Aug 2026' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next week' })).toBeDisabled()
  expect(requested).toEqual(['2026-08-16', '2026-08-23'])
})

test('a week in progress counts only the days that are over', async () => {
  renderScreen()
  await loaded()

  await userEvent.click(screen.getByRole('button', { name: 'Next week' }))

  expect(await screen.findByText(/count once they are over/)).toBeInTheDocument()
  // Sunday to Tuesday are over, and two of them were logged.
  expect(screen.getByText('2 of 3')).toBeInTheDocument()
  expect(screen.getByText('days over so far')).toBeInTheDocument()
  expect((await dayRow('Wed')).getByText('Today, not over yet')).toBeInTheDocument()
  expect((await dayRow('Thu')).getByText('Still to come')).toBeInTheDocument()
})

// --- the week's account ----------------------------------------------------------------

test('accounts for every meal slot of the week, and for the plan', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('6 of 7')).toBeInTheDocument()
  // Skipped is accounted for; only the slots with neither food nor a skip were missed.
  expect(screen.getByText('26 logged, 3 skipped, 6 missed')).toBeInTheDocument()
  expect(screen.getByText('17 of 28')).toBeInTheDocument()
})

test('says nothing about a plan when the week had none', async () => {
  stubReport({ ...REPORT_FIXTURE, plan: null })
  renderScreen()
  await loaded()

  expect(screen.queryByText('Plan followed')).not.toBeInTheDocument()
})

// A week largely eaten out must not be presented with false precision.
test('keeps estimated energy apart from measured energy', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('9,160 kcal')).toBeInTheDocument()
  expect(screen.getByText('2,980 kcal')).toBeInTheDocument()
  expect(screen.getByText('25% of the week’s energy, kept apart')).toBeInTheDocument()
})

// --- nutrients -------------------------------------------------------------------------

test('counts days met over the days that measured the nutrient', async () => {
  renderScreen()
  await loaded()

  expect(nutrientRow('Calcium').getByText('1 of 6')).toBeInTheDocument()
  // Fibre was measured on five of the six days logged.
  expect(nutrientRow('Dietary fibre').getByText('1 of 5')).toBeInTheDocument()
})

test('judges the week against its summed EAR and target, as Today judges a day', async () => {
  renderScreen()
  await loaded()

  // 296.4 g is short of the week's 323.7 g target but past its 257.4 g EAR.
  expect(nutrientRow('Protein').getByText('on target')).toBeInTheDocument()
  expect(nutrientRow('Calcium').getByText('under target')).toBeInTheDocument()
  expect(nutrientRow('Vitamin B12').getByText('over target')).toBeInTheDocument()
  // A ceiling's own figure is its limit: 14,820 mg against 12,000 mg.
  expect(nutrientRow('Sodium').getByText('past the upper limit')).toBeInTheDocument()
})

test('notes days past the upper limit apart from the week’s standing', async () => {
  stubReport({
    ...REPORT_FIXTURE,
    nutrients: REPORT_FIXTURE.nutrients.map((nutrient) => {
      if (nutrient.code === 'calcium') return { ...nutrient, days_over_limit: 2 }
      if (nutrient.code === 'iron') return { ...nutrient, days_over_limit: 1 }
      return nutrient
    }),
  })
  renderScreen()
  await loaded()

  expect(nutrientRow('Calcium').getByText('2 days over the limit')).toBeInTheDocument()
  expect(nutrientRow('Iron').getByText('1 day over the limit')).toBeInTheDocument()
  expect(nutrientRow('Protein').queryByText(/over the limit/)).not.toBeInTheDocument()
})

test('says how much of the food a figure speaks for', async () => {
  renderScreen()
  await loaded()

  expect(
    nutrientRow('Vitamin B12').getByText('Measured for 62% of what you ate'),
  ).toBeInTheDocument()
  expect(nutrientRow('Calcium').queryByText(/Measured for/)).not.toBeInTheDocument()
})

test('shows energy totals in whole kilocalories', async () => {
  renderScreen()
  await loaded()

  expect(nutrientRow('Energy').getByText('12,140')).toBeInTheDocument()
  expect(nutrientRow('Energy').getByText('12,002 kcal')).toBeInTheDocument()
})

// --- what could not be made up, and what to eat -----------------------------------------

/*
 * The report must show what could NOT be made up. Silently dropping an expired
 * shortfall would present a worse week as a better one, which is the exact
 * dishonesty the ledger's expiry record exists to prevent.
 */
test('reports shortfalls the ledger could not make up, and why', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('Calcium — 1,240 mg')).toBeInTheDocument()
  expect(screen.getByText('Beyond the 30% a day can carry, so it expired.')).toBeInTheDocument()
  expect(screen.getByText('Dietary fibre — 22.6 g')).toBeInTheDocument()
  expect(screen.getByText('Beyond the 25% a day can carry, so it expired.')).toBeInTheDocument()
  expect(
    screen.getByText('Protein has no storage pool, so a short day is not carried forward.'),
  ).toBeInTheDocument()
})

test('suggests dishes for what fell short', async () => {
  renderScreen()
  await loaded()

  expect(
    screen.getByText(
      'Calcium fell short this week. ' +
        'Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam.',
    ),
  ).toBeInTheDocument()
  const dishes = within(screen.getByRole('list', { name: 'Dishes for Calcium' }))
  expect(dishes.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    'Ragi mudde',
    'Curd rice',
    'Moong dal payasam',
  ])
})

test('says so when nothing expired and nothing needs suggesting', async () => {
  stubReport({ ...REPORT_FIXTURE, uncompensated: [], suggestions: [] })
  renderScreen()
  await loaded()

  expect(screen.getByText('No shortfall expired this week.')).toBeInTheDocument()
  expect(
    screen.getByText('No nutrient fell short on enough measured days to suggest a change.'),
  ).toBeInTheDocument()
})

// --- the energy chart --------------------------------------------------------------------

/*
 * A chart is unreadable to a screen reader, and Recharts renders SVG with no
 * text alternative. The same series is therefore also exposed as a table.
 */
test('the energy chart’s figures are a table, each day against its own target', async () => {
  renderScreen()

  const sunday = await dayRow('Sun')
  expect(sunday.getByText('2,240 kcal')).toBeInTheDocument()
  expect(sunday.getByText('2,105 kcal')).toBeInTheDocument()
  // Thursday's weigh-in stepped the target down from that day on.
  const thursday = await dayRow('Thu')
  expect(thursday.getByText('2,310 kcal')).toBeInTheDocument()
  expect(thursday.getByText('1,895 kcal')).toBeInTheDocument()
})

test('a day with nothing logged is not shown as a day of eating nothing', async () => {
  renderScreen()

  const tuesday = await dayRow('Tue')
  expect(tuesday.getByText('Nothing logged')).toBeInTheDocument()
  expect(tuesday.queryByText('0 kcal')).not.toBeInTheDocument()
})

// --- nothing to show -----------------------------------------------------------------------

test('an empty week says so instead of showing a week of zeros', async () => {
  stubReport({
    ...REPORT_FIXTURE,
    tracked_days: 0,
    slots: { logged: 0, skipped: 0, expected: 35 },
    measured_kcal: 0,
    estimated_kcal: 0,
    plan: null,
    days: REPORT_FIXTURE.days.map((day) => ({
      ...day,
      state: 'untracked' as const,
      energy_kcal: 0,
    })),
    nutrients: [],
    uncompensated: [],
    suggestions: [],
  })
  renderScreen()

  expect(await screen.findByText('Nothing was logged this week')).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  // An earlier week may have more, so the way back stays open.
  expect(screen.getByRole('button', { name: 'Previous week' })).toBeEnabled()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  stubStatus(404)
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// The browser's calendar can reach a Sunday before the account's timezone does.
test('says so when the week has not started where the account keeps time', async () => {
  stubStatus(422)
  renderScreen()

  expect(await screen.findByText('That week has not started yet')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('says when the report could not be loaded, and keeps the way to other weeks', async () => {
  stubStatus(500)
  renderScreen()

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/)
  expect(screen.getByRole('button', { name: 'Previous week' })).toBeEnabled()
})
```

- [ ] **Step 3: Run them to verify they fail**

Run: `npx vitest run src/report`
Expected: FAIL at collection: `Failed to resolve import "./useReport" from "src/report/ReportScreen.test.tsx". Does the file exist?`

- [ ] **Step 4: Implement**

Create `src/report/useReport.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { weekStartIso } from '../plan/usePlan'
import type { WeeklyReport } from './types'

export function useWeeklyReport(start: string) {
  return useQuery({
    queryKey: ['reports', 'week', start],
    queryFn: () => api.get<WeeklyReport>(`/reports/week?start=${start}`),
    retry: false,
  })
}

/** An ISO calendar date from a Date's local parts, never its UTC ones. */
function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/**
 * The calendar date `days` after an ISO date, negative for before.
 *
 * Built from its parts, like `formatDay`, because `new Date('2026-08-16')` is UTC
 * midnight, which is still the 15th anywhere west of Greenwich.
 */
export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return isoDate(new Date(year, month - 1, day + days))
}

/**
 * The Sunday before this week's Sunday. Its Saturday has ended, so it is the
 * latest week with a complete report. The week in progress would open on days
 * that count for nothing yet.
 */
export function lastCompleteWeekStart(from: Date = new Date()): string {
  return addDays(weekStartIso(from), -7)
}
```

Replace `src/report/EnergyChart.tsx`:

```tsx
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatAmount } from '../lib/format'
import type { DayState, ReportDay } from './types'

/** What a day without a reading says in place of a figure. */
const NO_READING: Record<Exclude<DayState, 'tracked'>, string> = {
  untracked: 'Nothing logged',
  'in-progress': 'Today, not over yet',
  future: 'Still to come',
}

function energyWords(day: ReportDay): string {
  return day.state === 'tracked'
    ? `${formatAmount(day.energy_kcal, 'kcal')} kcal`
    : NO_READING[day.state]
}

/**
 * A logged day is a solid bar in the status colour Today uses. A day without a
 * reading is an outline drawn to its target. A zero-height bar would draw it as a
 * day of eating nothing, which the diary cannot say. Dashed means nothing was
 * logged. Dotted and faint means the day is not over yet.
 */
function barStyle(day: ReportDay) {
  if (day.state === 'tracked') {
    return {
      fill: day.energy_kcal > day.target_kcal ? 'var(--color-over)' : 'var(--color-on-target)',
    }
  }
  const untracked = day.state === 'untracked'
  return {
    fill: 'transparent',
    stroke: 'var(--color-text-muted)',
    strokeWidth: 1.5,
    strokeDasharray: untracked ? '4 3' : '1 3',
    strokeOpacity: untracked ? 1 : 0.6,
  }
}

/**
 * Energy for each day against that day's own target.
 *
 * The target is a line through the week rather than one reference line.
 * - A recalibration moves it from the day it took effect, so an earlier day is
 *   never judged against a figure it did not have.
 * - Each figure is the day's base target, before any carry, which is what the
 *   backend reports.
 *
 * The chart is decorative for assistive technology (`aria-hidden`). The same
 * figures are published as a real table beside it, because Recharts emits SVG
 * with no text alternative.
 */
export function EnergyChart({ days }: { days: ReportDay[] }) {
  const data = days.map((day) => ({
    ...day,
    bar_kcal: day.state === 'tracked' ? day.energy_kcal : day.target_kcal,
  }))

  return (
    <>
      <div aria-hidden="true">
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" vertical={false} />
              <XAxis
                dataKey="weekday"
                tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <YAxis
                tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <Tooltip
                cursor={{ fill: 'var(--color-surface-alt)' }}
                contentStyle={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 6,
                  color: 'var(--color-text)',
                }}
                formatter={(value, name, item) =>
                  name === 'Target'
                    ? [`${formatAmount(Number(value ?? 0), 'kcal')} kcal`, name]
                    : [energyWords(item.payload as ReportDay), name]
                }
              />
              {/*
                Recharts animates bars up from zero on every mount. In a data-first
                design that is noise, it delays the figures being readable, and CSS
                `prefers-reduced-motion` cannot switch it off because the animation
                is driven in JavaScript.
              */}
              <Bar name="Energy" dataKey="bar_kcal" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {days.map((day) => (
                  <Cell key={day.date} {...barStyle(day)} />
                ))}
              </Bar>
              <Line
                name="Target"
                dataKey="target_kcal"
                type="step"
                stroke="var(--color-text-muted)"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          The dashed line is each day’s own target. An outlined bar is a day with nothing
          logged, or one not over yet.
        </p>
      </div>

      {/* The chart's data, for screen readers and for anyone who wants the figures. */}
      <table className="sr-only">
        <caption>Energy each day against that day’s target</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Energy</th>
            <th scope="col">Target</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{day.weekday}</th>
              <td>{energyWords(day)}</td>
              <td>{formatAmount(day.target_kcal, 'kcal')} kcal</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
```

Replace `src/report/ReportScreen.tsx`:

```tsx
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { formatAmount, formatDay, formatPercent, formatWithUnit, unitLabel } from '../lib/format'
import { nutrientStatus } from '../lib/status'
import { weekStartIso } from '../plan/usePlan'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { STATUS_LABELS, STATUS_TEXT } from '../ui/statusPresentation'
import { EnergyChart } from './EnergyChart'
import type {
  ReportNutrient,
  ReportStatus,
  Suggestion,
  UncompensatedGap,
  WeeklyReport,
} from './types'
import { addDays, lastCompleteWeekStart, useWeeklyReport } from './useReport'

const PROFILE_LINK = [
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent',
  'px-4 text-sm font-medium text-surface',
].join(' ')

// Below this, a figure speaks for only part of what was eaten, and the table says
// so. It is the threshold Today's bars use.
const FULL_COVERAGE = 0.995

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold">{value}</p>
      {hint !== undefined && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}

function WeekHeader({
  start,
  status,
  onMove,
}: {
  start: string
  status: ReportStatus | undefined
  onMove: (start: string) => void
}) {
  // The server refuses a week that has not started, so Next stops at this one.
  const atCurrentWeek = start >= weekStartIso()

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* Worked out from the week asked for, so it shows while the report loads. */}
        <h2 className="text-xl font-semibold">
          {`${formatDay(start)} – ${formatDay(addDays(start, 6))}`}
        </h2>
        {status === 'in-progress' && <Badge tone="accent">In progress</Badge>}
      </div>
      <div className="flex gap-2">
        <Button onClick={() => onMove(addDays(start, -7))}>
          <ChevronLeft className="size-4" aria-hidden="true" />
          Previous week
        </Button>
        <Button disabled={atCurrentWeek} onClick={() => onMove(addDays(start, 7))}>
          Next week
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  )
}

function overLimitWords(days: number): string {
  return days === 1 ? '1 day over the limit' : `${days} days over the limit`
}

function NutrientRow({ nutrient }: { nutrient: ReportNutrient }) {
  /*
   * The week's intake against its summed EAR and target: the DRI framework's own
   * "average daily intake over 1 or more weeks". A daily upper limit is never
   * summed into a weekly one, so it is left out here, and the days past it are
   * counted on their own. A ceiling's own figure is its limit, so a ceiling's week
   * is still set against its summed ceilings.
   */
  const status = nutrientStatus({
    consumed: nutrient.consumed_total,
    ear: nutrient.ear_total,
    rda: nutrient.target_total,
    tul: null,
    kind: nutrient.kind,
  })

  return (
    <tr className="border-b border-border last:border-b-0">
      <th scope="row" className="px-4 py-2 text-left font-medium">
        {nutrient.display_name}
      </th>
      <td className="px-4 py-2 text-right">
        {formatAmount(nutrient.consumed_total, nutrient.unit)}
      </td>
      <td className="px-4 py-2 text-right text-text-muted">
        {formatAmount(nutrient.target_total, nutrient.unit)} {unitLabel(nutrient.unit)}
      </td>
      <td className="px-4 py-2 text-right">
        {nutrient.days_met} of {nutrient.measured_days}
      </td>
      <td className="px-4 py-2">
        <span className={STATUS_TEXT[status]}>{STATUS_LABELS[status]}</span>
        {nutrient.days_over_limit > 0 && (
          <span className="block text-xs text-above-limit">
            {overLimitWords(nutrient.days_over_limit)}
          </span>
        )}
        {/*
          Partial coverage is reported rather than hidden, as on Today. The total
          speaks only for the food that carried a figure.
        */}
        {nutrient.coverage < FULL_COVERAGE && (
          <span className="block text-xs text-text-muted">
            {`Measured for ${Math.round(nutrient.coverage * 100)}% of what you ate`}
          </span>
        )}
      </td>
    </tr>
  )
}

function NutrientTable({ nutrients }: { nutrients: ReportNutrient[] }) {
  return (
    <Card className="overflow-x-auto p-0">
      <div className="border-b border-border px-4 py-3">
        <CardTitle>Nutrients across the week</CardTitle>
        <p className="mt-1 text-xs text-text-muted">
          Each total counts only the days your food carried a figure for it, so a gap in the
          food tables never reads as a shortfall.
        </p>
      </div>
      <table className="w-full text-sm">
        <caption className="sr-only">Nutrients across the week</caption>
        <thead>
          <tr className="border-b border-border text-left text-xs text-text-muted">
            <th scope="col" className="px-4 py-2 font-medium">Nutrient</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Intake</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Target</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Days met</th>
            <th scope="col" className="px-4 py-2 font-medium">Standing</th>
          </tr>
        </thead>
        <tbody>
          {nutrients.map((nutrient) => (
            <NutrientRow key={nutrient.code} nutrient={nutrient} />
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function Uncompensated({ gaps }: { gaps: UncompensatedGap[] }) {
  return (
    <Card>
      <CardTitle>What could not be made up</CardTitle>
      {gaps.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">No shortfall expired this week.</p>
      ) : (
        <ul className="mt-2 space-y-3">
          {gaps.map((gap) => (
            <li key={gap.code} className="text-sm">
              <span className="font-medium">
                {gap.display_name} — {formatWithUnit(gap.amount, gap.unit)}
              </span>
              <p className="text-text-muted">{gap.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Suggestions({ suggestions }: { suggestions: Suggestion[] }) {
  return (
    <Card>
      <CardTitle>What to eat next week</CardTitle>
      {suggestions.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">
          No nutrient fell short on enough measured days to suggest a change.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-text-muted">
            Dishes your plan can serve, that suit your diet and leave out the foods you avoid.
          </p>
          <ul className="mt-3 space-y-3">
            {suggestions.map((suggestion) => (
              <li key={suggestion.nutrient_code} className="text-sm">
                <p>{suggestion.text}</p>
                {suggestion.foods.length > 0 && (
                  <ul
                    aria-label={`Dishes for ${suggestion.display_name}`}
                    className="mt-1.5 flex flex-wrap gap-1.5"
                  >
                    {suggestion.foods.map((food) => (
                      <li key={food.food_id}>
                        <Badge tone="accent">{food.name}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

function ReportBody({ data }: { data: WeeklyReport }) {
  const inProgress = data.status === 'in-progress'

  if (data.tracked_days === 0) {
    return inProgress ? (
      <EmptyState
        title="Nothing to add up yet"
        description="A day counts here once it is over and something was logged in it."
      />
    ) : (
      <EmptyState
        title="Nothing was logged this week"
        description={
          'A day with nothing logged is left out of every total, rather than read as a ' +
          'day of eating nothing.'
        }
      />
    )
  }

  // The days that have ended. A day in progress, or still to come, counts in nothing.
  const elapsed = data.days.filter(
    (day) => day.state === 'tracked' || day.state === 'untracked',
  ).length
  const { logged, skipped, expected } = data.slots
  const estimatedShare = formatPercent(
    data.estimated_kcal,
    data.measured_kcal + data.estimated_kcal,
  )

  return (
    <>
      {inProgress && (
        <p className="text-sm text-text-muted">
          This week is still going. Today and the days after it count once they are over.
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
        <Figure
          label="Days logged"
          value={`${data.tracked_days} of ${elapsed}`}
          hint={inProgress ? 'days over so far' : 'across the week'}
        />
        <Figure
          label="Meals accounted for"
          value={`${logged + skipped} of ${expected}`}
          hint={`${logged} logged, ${skipped} skipped, ${expected - logged - skipped} missed`}
        />
        <Figure
          label="Measured"
          value={`${formatAmount(data.measured_kcal, 'kcal')} kcal`}
          hint="weighed or by household measure"
        />
        <Figure
          label="Estimated"
          value={`${formatAmount(data.estimated_kcal, 'kcal')} kcal`}
          hint={`${estimatedShare}% of the week’s energy, kept apart`}
        />
        {data.plan !== null && (
          <Figure
            label="Plan followed"
            value={`${data.plan.followed} of ${data.plan.planned}`}
            hint="planned meals eaten as planned"
          />
        )}
      </div>

      <Card>
        <CardTitle>Energy each day</CardTitle>
        <div className="mt-2">
          <EnergyChart days={data.days} />
        </div>
      </Card>

      <NutrientTable nutrients={data.nutrients} />
      <Uncompensated gaps={data.uncompensated} />
      <Suggestions suggestions={data.suggestions} />
    </>
  )
}

function WeekContent({ report }: { report: ReturnType<typeof useWeeklyReport> }) {
  if (report.isPending) return <Skeleton className="h-96 w-full" />

  // Only when this browser's calendar has reached a Sunday that the account's
  // timezone has not: the server counts weeks where the account is.
  if (report.error instanceof ApiError && report.error.status === 422) {
    return (
      <EmptyState
        title="That week has not started yet"
        description={
          'Weeks begin on Sunday in your account’s timezone, where it is still the ' +
          'week before.'
        }
      />
    )
  }
  if (report.isError || report.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        This week’s report could not be loaded. Please try again.
      </p>
    )
  }
  return <ReportBody data={report.data} />
}

export function ReportScreen() {
  const [start, setStart] = useState(() => lastCompleteWeekStart())
  const report = useWeeklyReport(start)

  /*
   * A 404 means there is no profile yet: a report is measured against the daily
   * targets, and there are none. Point at onboarding rather than reporting an
   * error that did not happen.
   */
  if (report.error instanceof ApiError && report.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description={
          'Your weekly report is measured against your daily targets, so there is ' +
          'nothing to report until you have told us about yourself.'
        }
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }

  return (
    <section className="space-y-4">
      <WeekHeader start={start} status={report.data?.status} onMove={setStart} />
      <WeekContent report={report} />
    </section>
  )
}
```

- [ ] **Step 5: Run the tests and the checks**

Run: `npx vitest run && npx tsc -b && npm run lint && npm run build`
Expected: all PASS and clean, including the 25 tests in `src/report/ReportScreen.test.tsx`. No other test used the deleted report handler. The build still emits the Report screen as its own chunk, because `App.tsx` still loads it lazily.

- [ ] **Step 6: Commit**

```bash
git add src/report/types.ts src/report/useReport.ts src/report/ReportScreen.tsx \
  src/report/EnergyChart.tsx src/report/ReportScreen.test.tsx \
  src/mocks/fixtures/report.ts src/mocks/handlers/index.ts
git commit -m "feat(frontend): put the Report screen on the real endpoint

The report opens on the last complete week, with previous and next buttons
that stop at the week in progress. A week still going says so, and counts
only the days that are over.

Every figure is now the backend's: days logged; meals logged, skipped and
missed; measured energy kept apart from estimated; and the plan followed,
when there was one. Days met are counted over the days that measured a
nutrient. The week's standing sets its intake against the summed EAR and
target, as Today does for a day. Days past an upper limit are noted apart,
because a daily limit summed over a week means nothing. Each shortfall that
expired says why, and each suggestion names the dishes it proposes.

The energy chart draws each day against its own target, so a mid-week
recalibration moves the line from that day on. A day with nothing logged is
an outline rather than a zero bar, because silence is not a day of eating
nothing. The table behind the chart says the same in words.

The report's MSW handler and its demo banner are gone.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `reminder_on` survives a profile save

`reminder_on` is stored on the profile's `meal_slot_times` rows. Every profile save deletes those rows and inserts them again from the payload. `MealTimeIn.reminder_on` defaults to true, and the wizard never sends it. So today, saving any section of the profile turns every reminder back on. That includes the mid-morning snack, which Task 3's data step has just turned off, and anything the Reminders screen will set from Task 10 onward.

This task makes the field optional:
- A save that leaves it out keeps the slot's saved setting.
- A slot with no saved setting gets the default. The default is on, except for the mid-morning snack, which the spec says "shouldn't nag someone who rarely eats it".
- An explicit value still wins.

The wizard carries the field from the saved profile through to the next save, as it does every other field. The server rule still matters for any client that predates the field, such as a PWA still running a cached bundle.

**Files:**
- Modify (backend): `app/profiles/router.py` (`MealTimeIn`), `app/profiles/service.py` (`save_profile`)
- Modify (frontend):
  - `src/onboarding/types.ts` (`MealTimeAnswer.reminder_on`)
  - `src/onboarding/validation.ts` (`emptyAnswers`)
  - `src/onboarding/useProfile.ts` (`answersFromProfile`)
  - `src/onboarding/OnboardingWizard.tsx` (a save also refreshes the Reminders screen)
- Test: `backend/tests/test_tracking_api.py` (append), `frontend/src/onboarding/useProfile.test.ts` (append), `frontend/src/onboarding/validation.test.ts` (append)

`src/onboarding/steps.tsx` needs no change. Every edit in the meal-times step spreads the row (`{ ...existing, is_enabled: checked }`), so `reminder_on` is kept through each edit.

**Interfaces:**
- Consumes:
  - Task 3's data step, which leaves existing mid-morning snack rows with `reminder_on` false. This task is what keeps them false through the next save.
  - `profiles.get_meal_times` (existing).
- Produces:
```python
# app/profiles/router.py
class MealTimeIn(BaseModel):
    slot: str
    time: str
    weekend_time: str | None = None
    reminder_on: bool | None = None     # None, or absent: keep the slot's saved setting
    is_enabled: bool = True

# app/profiles/service.py -- save_profile(db, user, payload) keeps its signature.
# Per slot, reminder_on is: the payload's value when not None; else the slot's saved
# row's; else slot != "snack1" (a new slot). Task 10 relies on exactly this.
```
```ts
// src/onboarding/types.ts
export interface MealTimeAnswer {
  slot: MealSlot; time: string; weekend_time: string | null
  reminder_on: boolean
  is_enabled: boolean
}
// src/onboarding/validation.ts
export function reminderOnByDefault(slot: MealSlot): boolean   // slot !== 'snack1'
```
- A profile save now also invalidates `['settings', 'reminders']`, the Reminders screen's query key. Task 12 keeps that key.

- [ ] **Step 1: Write the failing tests**

Append to the end of `backend/tests/test_tracking_api.py`. It needs no new imports.

```python


# --- a reminder setting survives a profile save ------------------------------
#
# `reminder_on` is the Reminders screen's setting, but it lives on the meal-time
# rows that every profile save deletes and re-inserts. A save that leaves it out
# keeps each slot's setting; a slot with none gets the default -- on, except the
# mid-morning snack, which the spec says should not nag someone who rarely eats it.


def meal_times_without_reminders() -> list[dict]:
    """PROFILE's meal times as a client that predates `reminder_on` sends them."""
    return [
        {key: value for key, value in item.items() if key != "reminder_on"}
        for item in PROFILE["meal_times"]
    ]


def reminders_saved(client) -> dict[str, bool]:
    meal_times = client.get("/profile").json()["meal_times"]
    return {item["slot"]: item["reminder_on"] for item in meal_times}


def test_a_save_that_omits_reminders_keeps_each_slots_setting(signed_in):
    lunch_off = [
        {**item, "reminder_on": False} if item["slot"] == "lunch" else item
        for item in PROFILE["meal_times"]
    ]
    signed_in.put("/profile", json={**PROFILE, "meal_times": lunch_off})

    response = signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times_without_reminders()}
    )

    assert response.status_code == 200
    # Lunch was switched off, and the mid-morning snack came in off with PROFILE.
    assert reminders_saved(signed_in) == {
        "breakfast": True,
        "snack1": False,
        "lunch": False,
        "snack2": True,
        "dinner": True,
    }


def test_a_new_profile_has_no_mid_morning_snack_reminder(signed_in):
    signed_in.put("/profile", json={**PROFILE, "meal_times": meal_times_without_reminders()})

    assert reminders_saved(signed_in) == {
        "breakfast": True,
        "snack1": False,
        "lunch": True,
        "snack2": True,
        "dinner": True,
    }


def test_a_reminder_the_payload_sets_is_honoured(signed_in):
    """A saved setting fills a gap in the payload; it never overrules it."""
    signed_in.put("/profile", json=PROFILE)
    flipped = [
        {**item, "reminder_on": not item["reminder_on"]}
        if item["slot"] in {"snack1", "dinner"}
        else item
        for item in PROFILE["meal_times"]
    ]

    signed_in.put("/profile", json={**PROFILE, "meal_times": flipped})

    assert reminders_saved(signed_in) == {
        "breakfast": True,
        "snack1": True,
        "lunch": True,
        "snack2": True,
        "dinner": False,
    }
```

The tests read the settings back through `GET /profile`, whose `meal_times` come back in random primary-key order, so they compare dicts. None of them depends on today. Each save records a weigh-in dated the real today (plan 7), which does not affect these tests.

Append to `frontend/src/onboarding/useProfile.test.ts`:

```ts

function mealTime(slot: string, reminder_on: boolean) {
  return { slot, time: '08:00', weekend_time: null, reminder_on, is_enabled: true }
}

// The Reminders screen sets reminder_on, but it rides on the meal-time rows that
// PUT /profile rewrites. Carried here, a save of any other section sends each
// slot's setting back as it was.
test('each slot keeps its saved reminder setting', () => {
  const answers = answersFromProfile(
    savedProfile({
      meal_times: [
        mealTime('breakfast', true),
        mealTime('snack1', true),
        mealTime('lunch', false),
        mealTime('snack2', true),
        mealTime('dinner', true),
      ],
    }),
  )

  expect(answers.meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', true],
    ['lunch', false],
    ['snack2', true],
    ['dinner', true],
  ])
})

test('a slot with no saved row gets the default reminder', () => {
  const answers = answersFromProfile(savedProfile({ meal_times: [] }))

  expect(answers.meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', false],
    ['lunch', true],
    ['snack2', true],
    ['dinner', true],
  ])
})
```

Append to `frontend/src/onboarding/validation.test.ts`, which already tests `emptyAnswers`' meal times:

```ts

// The spec's own example: the optional mid-morning snack should not nag someone
// who rarely eats it. So its reminder starts off, and every other slot's on.
test('a new questionnaire reminds about every meal but the mid-morning snack', () => {
  expect(emptyAnswers().meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', false],
    ['lunch', true],
    ['snack2', true],
    ['dinner', true],
  ])
})
```

- [ ] **Step 2: Run them to verify they fail**

From `backend/`, run: `uv run pytest tests/test_tracking_api.py -q -k reminder`

Expected: 2 failed, 1 passed.
- `test_a_save_that_omits_reminders_keeps_each_slots_setting` fails. Its dict assertion shows `{'snack1': True} != {'snack1': False}` and `{'lunch': True} != {'lunch': False}`, because the omitted field defaulted to true.
- `test_a_new_profile_has_no_mid_morning_snack_reminder` fails on `{'snack1': True} != {'snack1': False}`.
- `test_a_reminder_the_payload_sets_is_honoured` already passes, because explicit values were always stored. It guards the fix: a saved setting must not overrule an explicit one.

From `frontend/`, run: `npx vitest run src/onboarding/useProfile.test.ts src/onboarding/validation.test.ts`

Expected: the 3 new tests FAIL with `expected [ [ 'breakfast', undefined ], …(4) ] to deeply equal [ [ 'breakfast', true ], …(4) ]`, because no answer carries `reminder_on` yet. The other 22 pass. Vitest does not type-check, so the missing property shows up as `undefined` rather than as a compile error.

- [ ] **Step 3: Keep the saved setting on the backend**

In `backend/app/profiles/router.py`, in `MealTimeIn`, replace the line `    reminder_on: bool = True` with:

```python
    # None keeps the slot's saved setting, which belongs to the Reminders screen: a
    # client that says nothing about it -- the wizard before plan 8, and a PWA still
    # running that bundle -- must not switch every reminder back on. A slot with no
    # saved setting gets the default: on, except the mid-morning snack.
    reminder_on: bool | None = None
```

The comment below it, "Defaults to on, so a client that predates the field…", belongs to `is_enabled` and stays where it is.

In `backend/app/profiles/service.py`:

1. Replace the top of `save_profile`, from `def save_profile(` down to and including the `CHILD_MODELS` delete loop, with the block below. The previous settings have to be read before that loop, because the rows are gone once it has run.

```python
def save_profile(db: Session, user: User, payload) -> Profile:
    """Replace the profile and everything hanging off it.

    Onboarding submits the whole questionnaire at once, so a save is a wholesale
    replacement rather than a merge — otherwise a condition the user unticked
    would linger and keep changing their targets.

    The one exception is a slot's reminder. The Reminders screen sets it and the
    questionnaire never asks, so a payload that leaves it out keeps the slot's
    saved setting, and a slot with none gets the default.
    """
    # Read before the delete below, which leaves no row to read it from. Kept as
    # plain values: the bulk delete takes the session's row objects with it.
    reminders = {row.slot: row.reminder_on for row in get_meal_times(db, user)}

    for model in CHILD_MODELS:
        db.execute(delete(model).where(model.user_id == user.id))
```

2. In the `MealSlotTime(...)` construction, replace `reminder_on=item.reminder_on,` with:

```python
                reminder_on=_reminder_on(item, reminders),
```

3. Add these two helpers directly above `_as_time`:

```python
def _reminder_on(item, saved: dict[str, bool]) -> bool:
    """The payload's setting, else the slot's saved one, else a new slot's default."""
    if item.reminder_on is not None:
        return item.reminder_on
    return saved.get(item.slot, _reminder_by_default(item.slot))


def _reminder_by_default(slot: str) -> bool:
    # The spec's own example: the optional mid-morning snack should not nag someone
    # who rarely eats it, so its reminder is opt-in.
    return slot != "snack1"
```

A JSON `null` for `reminder_on` means the same as leaving it out.

- [ ] **Step 4: Carry the setting through the wizard**

In `frontend/src/onboarding/types.ts`, in `MealTimeAnswer`, directly after `weekend_time: string | null`, add:

```ts
  /**
   * Whether this slot sends a reminder. The Reminders screen sets it; the wizard
   * only carries it from the saved profile to the next save, since `PUT /profile`
   * rewrites every meal-time row.
   */
  reminder_on: boolean
```

In `frontend/src/onboarding/validation.ts`, directly after the closing `}` of `DEFAULT_MEAL_TIMES`, add:

```ts

/**
 * Whether a slot reminds when nothing is saved for it yet. The optional
 * mid-morning snack should not nag someone who rarely eats it, so its reminder
 * is opt-in. Mirrors the default the backend gives a new meal-time row.
 */
export function reminderOnByDefault(slot: MealSlot): boolean {
  return slot !== 'snack1'
}
```

Then, in `emptyAnswers()`'s `meal_times` map, add this line directly after `weekend_time: null,`:

```ts
      reminder_on: reminderOnByDefault(slot),
```

In `frontend/src/onboarding/useProfile.ts`:
- Replace `import { DEFAULT_MEAL_TIMES, emptyAnswers } from './validation'` with:

```ts
import { DEFAULT_MEAL_TIMES, emptyAnswers, reminderOnByDefault } from './validation'
```

- In `answersFromProfile`'s `meal_times` map, directly after `weekend_time: item?.weekend_time ?? null,`, add:

```ts
        // The saved setting, so a save leaves the Reminders screen's choice as it
        // was; a slot the saved profile has no row for gets a new slot's default.
        reminder_on: item?.reminder_on ?? reminderOnByDefault(slot),
```

`SavedProfile.meal_times` already declares `reminder_on: boolean`, so it needs no change.

In `frontend/src/onboarding/OnboardingWizard.tsx`, in `useSaveProfile`'s `onSuccess`, directly after `queryClient.invalidateQueries({ queryKey: ['cycle'] })`, add:

```ts
      // The Reminders screen lists the slots a normal day has, at the times saved here.
      queryClient.invalidateQueries({ queryKey: ['settings', 'reminders'] })
```

No other code builds a `MealTimeAnswer` literal. `MealTimesStep.test.tsx` spreads `emptyAnswers()`, and the `SavedProfile` fixtures already carry `reminder_on`. So `tsc` has nothing else to flag.

- [ ] **Step 5: Run the tests and the checks**

From `backend/`, run: `uv run pytest tests/test_tracking_api.py tests/test_preferences_api.py -q && uv run ruff check .`

Expected: all PASS, and ruff clean. Both suites save profiles that send `reminder_on` for every slot, and explicit values behave as before.

From `frontend/`, run: `npx vitest run && npx tsc -b && npm run lint`

Expected: all PASS and clean.

- [ ] **Step 6: Commit**

From the repository root:

```bash
git add backend/app/profiles/router.py backend/app/profiles/service.py \
  backend/tests/test_tracking_api.py \
  frontend/src/onboarding/types.ts frontend/src/onboarding/validation.ts \
  frontend/src/onboarding/useProfile.ts frontend/src/onboarding/OnboardingWizard.tsx \
  frontend/src/onboarding/useProfile.test.ts frontend/src/onboarding/validation.test.ts
git commit -m "fix: keep each meal's reminder setting across a profile save

reminder_on lives on the meal-time rows that every profile save deletes and
re-inserts, and MealTimeIn defaulted it to true while the wizard never sent
it. A save of any section therefore switched every reminder back on,
including the mid-morning snack's, which the last migration turned off.

The field is now optional. A save that leaves it out keeps the slot's saved
setting, read before the rows are deleted, and a slot with none gets the
default: on, except the mid-morning snack, which the spec says should not
nag someone who rarely eats it. An explicit value still wins. The server
rule is what protects a PWA still running an older bundle.

The wizard carries the setting from the saved profile to the next save, as
it does every other field, and a new questionnaire starts with the snack's
reminder off. A save also refreshes the Reminders screen, since it can
change which slots a day has and when they are.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Reminder settings and push subscriptions, over HTTP

This task puts the Reminders screen's two halves behind HTTP. It sends nothing yet: Task 11 decides when a slot is due and pushes to it. A reminder setting is not a table of its own. `reminder_on` already sits on the profile's `meal_slot_times` rows, so the settings routes read and switch it there, in place, and a reminder fires at the time the diary shows and the planner plans for. A device is a `push_subscriptions` row, keyed by its endpoint. It belongs to the user, not the profile, so the profile save that replaces every meal-time row leaves it subscribed. The subscribe call is also the only thing that writes `users.timezone`, from the browser's own zone.

**Files:**
- Create: `app/reminders/__init__.py` (empty), `app/reminders/service.py`, `app/reminders/router.py`, `.env.example`
- Modify: `app/config.py` (the VAPID and scheduler settings), `app/main.py` (mount both routers)
- Test: `tests/test_reminders_api.py` (create)

**Interfaces:**
- Consumes:
  - Task 3: `PushSubscription(user_id, endpoint, p256dh: String(200), auth: String(100), user_agent: String(300) | None)` and its named constraint `uq_push_endpoint`, which the upsert targets.
  - Task 9: a profile save that omits `reminder_on` keeps each slot's previous value, and a new slot defaults to `slot != "snack1"`.
  - `profiles.get_profile`, `profiles.get_meal_times` (primary-key order, which is random), and `app.meal_slots.SLOTS` / `DEFAULT_SLOT_TIMES`.
- Produces:
```python
# app/config.py Settings
vapid_public_key: str = ""
vapid_private_key: str = ""
vapid_subject: str = "mailto:admin@example.com"
scheduler_enabled: bool = False

# app/reminders/service.py
class NoProfile(LookupError)            # raised by reminder_slots and set_reminder
class UnknownSlot(ValueError)           # a slot not in SLOTS, or one switched off in the profile
@dataclass(frozen=True)
class SlotReminder:
    slot: str; time: datetime.time; weekend_time: datetime.time | None; reminder_on: bool
def reminder_slots(db, user) -> list[SlotReminder]
    # enabled slots, SLOTS order; a slot with no row is on, at DEFAULT_SLOT_TIMES, with
    # reminder_on = slot != "snack1"
def set_reminder(db, user, slot: str, on: bool) -> None
    # edits the row in place, or creates it at the default time (is_enabled true)
def save_subscription(db, user, endpoint: str, p256dh: str, auth: str,
                      user_agent: str | None, timezone: str | None) -> PushSubscription
    # INSERT ... ON CONFLICT ON CONSTRAINT uq_push_endpoint DO UPDATE (user_id moves);
    # user_agent cut to 300; user.timezone set only when ZoneInfo resolves it
def delete_subscription(db, user, endpoint: str) -> bool   # False when not this user's
def device_count(db, user) -> int
```
- The HTTP contract that Task 12 writes into `frontend/src/settings/types.ts`. Every route answers 401 without a session.

| Method and path | Body | Answer |
|---|---|---|
| `GET /settings/reminders` | — | 200 `RemindersOut`; 404 with no profile |
| `PATCH /settings/reminders` | `{slot, reminder_on}` | 200 `RemindersOut`; 422 for an unknown or switched-off slot; 404 with no profile |
| `GET /push/public-key` | — | 200 `{key}`; 503 "Reminders are not set up on this server" while either VAPID key is unset |
| `POST /push/subscriptions` | `{endpoint: "https://…", keys: {p256dh, auth}, timezone?}` | 201 `{devices}`; 422 for a non-https endpoint, or keys missing or wider than their columns |
| `DELETE /push/subscriptions` | `{endpoint}` | 204; 404 when the endpoint is not this user's |

```
RemindersOut {
  slots: [{slot, time: "HH:MM", weekend_time: "HH:MM" | null, reminder_on}]   # enabled, SLOTS order
  devices: int                                                                # this user's browsers
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminders_api.py`:

```python
"""Reminder settings and push subscriptions, over HTTP.

The settings are the profile's own meal-time rows, edited in place, so a
reminder fires at the time the diary shows and the planner plans for. The
devices belong to the user, not the profile: a profile save replaces every
meal-time row, and must never unsubscribe a phone.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.profile import MealSlotTime
from app.models.push import PushSubscription
from app.models.user import User
from app.profiles import service as profiles
from app.reminders import service as reminders
from tests.test_tracking_api import PROFILE

ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-one"
KEYS = {"p256dh": "B" + "p" * 86, "auth": "a" * 22}

# What a profile saved before meal times existed reminds about: every slot at its
# default time, and the mid-morning snack opt-in.
DEFAULTS = [
    {"slot": "breakfast", "time": "08:00", "weekend_time": None, "reminder_on": True},
    {"slot": "snack1", "time": "11:00", "weekend_time": None, "reminder_on": False},
    {"slot": "lunch", "time": "13:30", "weekend_time": None, "reminder_on": True},
    {"slot": "snack2", "time": "17:00", "weekend_time": None, "reminder_on": True},
    {"slot": "dinner", "time": "20:30", "weekend_time": None, "reminder_on": True},
]


def subscription(endpoint: str = ENDPOINT, **extra) -> dict:
    return {"endpoint": endpoint, "keys": KEYS, **extra}


def meal_times(**changes: dict) -> list[dict]:
    """PROFILE's meal times, with the named slots' fields changed."""
    return [{**item, **changes.get(item["slot"], {})} for item in PROFILE["meal_times"]]


def slot_named(payload: dict, slot: str) -> dict:
    return next(item for item in payload["slots"] if item["slot"] == slot)


def profile_slot(client, slot: str) -> dict:
    """The slot as the profile reads it back, disabled slots included."""
    return slot_named({"slots": client.get("/profile").json()["meal_times"]}, slot)


def turn(client, slot: str, on: bool):
    return client.patch("/settings/reminders", json={"slot": slot, "reminder_on": on})


def unsubscribe(client, endpoint: str = ENDPOINT):
    return client.request("DELETE", "/push/subscriptions", json={"endpoint": endpoint})


def the_row(db) -> PushSubscription:
    return db.scalars(select(PushSubscription).where(PushSubscription.endpoint == ENDPOINT)).one()


def someone_elses_device(db, endpoint: str = ENDPOINT) -> User:
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(PushSubscription(user_id=other.id, endpoint=endpoint, p256dh="q" * 87, auth="b" * 22))
    db.flush()
    return other


@pytest.fixture
def me(signed_in, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def vapid(monkeypatch):
    """A configured server. Set explicitly: a developer's .env may carry real keys."""
    monkeypatch.setattr(settings, "vapid_public_key", "BPublicKeyForTests")
    monkeypatch.setattr(settings, "vapid_private_key", "private-key-for-tests")


# --- settings --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/settings/reminders", None),
        ("PATCH", "/settings/reminders", {"slot": "lunch", "reminder_on": False}),
        ("GET", "/push/public-key", None),
        ("POST", "/push/subscriptions", subscription()),
        ("DELETE", "/push/subscriptions", {"endpoint": ENDPOINT}),
    ],
)
def test_reminder_routes_need_a_session(api_client, method, path, body):
    assert api_client.request(method, path, json=body).status_code == 401


def test_reminder_settings_need_a_profile(signed_in):
    response = signed_in.get("/settings/reminders")

    assert response.status_code == 404
    assert response.json()["detail"] == "Complete your profile first"
    assert turn(signed_in, "lunch", False).status_code == 404


def test_the_settings_are_the_profiles_meal_times(signed_in):
    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json() == {
        "slots": PROFILE["meal_times"],
        "devices": 0,
    }


def test_the_slots_come_in_meal_order_not_row_order(signed_in, me, db):
    """The profile's meal times read back in primary-key order, and the keys are random."""
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})
    for n, slot in enumerate(reversed(SLOTS), start=1):
        db.add(
            MealSlotTime(
                id=uuid.UUID(int=n),
                user_id=me.id,
                slot=slot,
                usual_time=datetime.time.fromisoformat(DEFAULT_SLOT_TIMES[slot]),
            )
        )
    db.flush()
    assert [row.slot for row in profiles.get_meal_times(db, me)] == list(reversed(SLOTS))

    slots = signed_in.get("/settings/reminders").json()["slots"]

    assert [item["slot"] for item in slots] == list(SLOTS)


def test_a_weekend_time_comes_through(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(breakfast={"weekend_time": "09:30"})}
    )

    breakfast = slot_named(signed_in.get("/settings/reminders").json(), "breakfast")

    assert breakfast == {
        "slot": "breakfast",
        "time": "08:00",
        "weekend_time": "09:30",
        "reminder_on": True,
    }


def test_a_switched_off_snack_has_no_reminder_to_set(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack2={"is_enabled": False})}
    )

    slots = signed_in.get("/settings/reminders").json()["slots"]

    assert [item["slot"] for item in slots] == ["breakfast", "snack1", "lunch", "dinner"]


def test_a_profile_without_meal_times_reminds_at_the_default_times(signed_in):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    assert signed_in.get("/settings/reminders").json()["slots"] == DEFAULTS


def test_a_reminder_can_be_turned_off(signed_in):
    signed_in.put("/profile", json=PROFILE)

    response = turn(signed_in, "lunch", False)

    assert response.status_code == 200
    assert slot_named(response.json(), "lunch") == {
        "slot": "lunch",
        "time": "13:30",
        "weekend_time": None,
        "reminder_on": False,
    }
    # One setting, on the row the profile reads -- not a copy that could drift.
    assert profile_slot(signed_in, "lunch")["reminder_on"] is False


def test_turning_a_reminder_on_leaves_the_times_alone(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack1={"weekend_time": "11:30"})}
    )

    snack1 = slot_named(turn(signed_in, "snack1", True).json(), "snack1")

    assert snack1 == {
        "slot": "snack1",
        "time": "11:00",
        "weekend_time": "11:30",
        "reminder_on": True,
    }


def test_a_reminder_set_before_meal_times_existed_gets_one_row(signed_in, me, db):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    assert turn(signed_in, "dinner", False).status_code == 200
    # The second call must update the row the first created, not insert another.
    response = turn(signed_in, "dinner", True)

    assert response.status_code == 200
    assert slot_named(response.json(), "dinner") == {
        "slot": "dinner",
        "time": "20:30",
        "weekend_time": None,
        "reminder_on": True,
    }
    rows = db.scalars(select(MealSlotTime).where(MealSlotTime.user_id == me.id)).all()
    assert [(row.slot, row.is_enabled, row.reminder_on) for row in rows] == [("dinner", True, True)]


def test_turning_one_reminder_off_leaves_the_rest_at_their_defaults(signed_in):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    slots = turn(signed_in, "breakfast", False).json()["slots"]

    assert slots == [{**DEFAULTS[0], "reminder_on": False}, *DEFAULTS[1:]]


def test_an_unknown_slot_is_refused(signed_in):
    signed_in.put("/profile", json=PROFILE)
    assert turn(signed_in, "brunch", True).status_code == 422


def test_a_switched_off_snack_cannot_be_given_a_reminder(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack2={"is_enabled": False})}
    )

    response = turn(signed_in, "snack2", False)

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]
    snack2 = profile_slot(signed_in, "snack2")
    assert snack2["is_enabled"] is False
    assert snack2["reminder_on"] is True


def test_a_profile_save_keeps_a_reminder_turned_off_here(signed_in):
    signed_in.put("/profile", json=PROFILE)
    turn(signed_in, "lunch", False)

    # An edit that says nothing about reminders, as the wizard's did until this plan.
    silent = [{k: v for k, v in item.items() if k != "reminder_on"} for item in meal_times()]
    signed_in.put("/profile", json={**PROFILE, "meal_times": silent})

    slots = signed_in.get("/settings/reminders").json()["slots"]
    assert {item["slot"]: item["reminder_on"] for item in slots} == {
        "breakfast": True,
        "snack1": False,
        "lunch": False,
        "snack2": True,
        "dinner": True,
    }


# --- the server's key ------------------------------------------------------------------


def test_the_public_key_is_handed_to_the_browser(signed_in, vapid):
    response = signed_in.get("/push/public-key")

    assert response.status_code == 200
    assert response.json() == {"key": "BPublicKeyForTests"}


@pytest.mark.parametrize("unset", ["vapid_public_key", "vapid_private_key"])
def test_without_both_keys_reminders_are_not_set_up(signed_in, vapid, monkeypatch, unset):
    monkeypatch.setattr(settings, unset, "")

    response = signed_in.get("/push/public-key")

    assert response.status_code == 503
    assert response.json()["detail"] == "Reminders are not set up on this server"


# --- devices ---------------------------------------------------------------------------


def test_subscribing_a_device_counts_it(signed_in):
    signed_in.put("/profile", json=PROFILE)

    response = signed_in.post("/push/subscriptions", json=subscription())

    assert response.status_code == 201
    assert response.json() == {"devices": 1}
    assert signed_in.get("/settings/reminders").json()["devices"] == 1


def test_a_second_browser_is_a_second_device(signed_in):
    signed_in.post("/push/subscriptions", json=subscription())
    response = signed_in.post("/push/subscriptions", json=subscription(f"{ENDPOINT}-laptop"))
    assert response.json() == {"devices": 2}


def test_resubscribing_a_browser_replaces_its_keys(signed_in, db):
    signed_in.post("/push/subscriptions", json=subscription())
    fresh = {"endpoint": ENDPOINT, "keys": {"p256dh": "C" + "r" * 86, "auth": "c" * 22}}

    assert signed_in.post("/push/subscriptions", json=fresh).json() == {"devices": 1}
    row = the_row(db)
    assert (row.p256dh, row.auth) == ("C" + "r" * 86, "c" * 22)


def test_a_browser_subscribed_from_another_account_moves_to_this_one(signed_in, me, db):
    """A shared phone reminds only whoever subscribed it last."""
    other = someone_elses_device(db)

    assert signed_in.post("/push/subscriptions", json=subscription()).json() == {"devices": 1}
    assert the_row(db).user_id == me.id
    assert reminders.device_count(db, other) == 0


def test_only_this_users_devices_are_counted(signed_in, db):
    someone_elses_device(db, f"{ENDPOINT}-theirs")
    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json()["devices"] == 0


def test_a_profile_save_leaves_the_devices_subscribed(signed_in):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/push/subscriptions", json=subscription())

    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json()["devices"] == 1


def test_subscribing_records_the_browsers_timezone(signed_in):
    signed_in.post("/push/subscriptions", json=subscription(timezone="Europe/London"))
    assert signed_in.get("/auth/me").json()["timezone"] == "Europe/London"


@pytest.mark.parametrize("timezone", ["Not/AZone", "", "../../etc/passwd"])
def test_a_timezone_this_server_cannot_resolve_is_ignored(signed_in, timezone):
    response = signed_in.post("/push/subscriptions", json=subscription(timezone=timezone))

    assert response.status_code == 201
    assert signed_in.get("/auth/me").json()["timezone"] == "Asia/Kolkata"


def test_no_timezone_leaves_the_users_alone(signed_in):
    signed_in.post("/push/subscriptions", json=subscription())
    assert signed_in.get("/auth/me").json()["timezone"] == "Asia/Kolkata"


def test_the_user_agent_is_cut_to_fit(signed_in, db):
    agent = "Mozilla/5.0 " + "x" * 400

    response = signed_in.post(
        "/push/subscriptions", json=subscription(), headers={"User-Agent": agent}
    )

    assert response.status_code == 201
    assert the_row(db).user_agent == agent[:300]


@pytest.mark.parametrize(
    "body",
    [
        # Plain http: the server would POST wherever this points.
        {"endpoint": "http://localhost:8000/admin", "keys": KEYS},
        {"endpoint": ENDPOINT},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "", "auth": "a" * 22}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "p" * 201, "auth": "a" * 22}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "p" * 87, "auth": "a" * 101}},
    ],
)
def test_a_malformed_subscription_is_refused(signed_in, me, db, body):
    assert signed_in.post("/push/subscriptions", json=body).status_code == 422
    assert reminders.device_count(db, me) == 0


def test_unsubscribing_forgets_the_device(signed_in, me, db):
    signed_in.post("/push/subscriptions", json=subscription())

    assert unsubscribe(signed_in).status_code == 204
    assert reminders.device_count(db, me) == 0


def test_someone_elses_device_cannot_be_unsubscribed(signed_in, db):
    other = someone_elses_device(db)

    assert unsubscribe(signed_in).status_code == 404
    assert reminders.device_count(db, other) == 1


def test_unsubscribing_an_unknown_device_is_not_found(signed_in):
    assert unsubscribe(signed_in).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_reminders_api.py -q`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'app.reminders'`

- [ ] **Step 3: The settings, and where they are documented**

In `app/config.py`, add below `frontend_origin: str = "http://localhost:5173"`:

```python
    # Web push (VAPID). With either key empty, reminders are off on this server:
    # GET /push/public-key answers 503 and the Reminders screen says so. Both are
    # base64url strings; .env.example says how to generate a pair.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    # Who a push service contacts about this sender: a mailto: or https: URL.
    vapid_subject: str = "mailto:admin@example.com"

    # Sends reminders from the API process, checking every minute. Off by default:
    # every API test's TestClient runs the app's lifespan, and a loop there would
    # read the development database.
    scheduler_enabled: bool = False
```

There is no `.env.example` yet. Create `.env.example` in `backend/`, next to `.env`. Every line is commented out, so copying it to `.env` changes nothing until a line is uncommented. That is deliberate: an empty `SESSION_SECRET=` would replace the development default with an empty secret, and an empty `COOKIE_SECURE=` would fail to parse as a bool.

```
# Copy to backend/.env and uncomment what you need. Every setting has a
# development default in app/config.py; the database URLs point at
# docker-compose's Postgres on port 5433.

# DATABASE_URL=postgresql+psycopg://healthmonitor:healthmonitor@localhost:5433/healthmonitor
# TEST_DATABASE_URL: the same, ending in /healthmonitor_test.

# The OAuth client ID behind the frontend's Google sign-in button.
# GOOGLE_CLIENT_ID=

# Local development only. Generate a real secret before deploying:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
# SESSION_SECRET=
# COOKIE_SECURE=true

# FRONTEND_ORIGIN=http://localhost:5173

# --- Meal reminders, by web push ---------------------------------------------
# With either key unset, reminders are off on this server and the Reminders
# screen says so. Generate a pair once with
#   npx web-push generate-vapid-keys
# and paste its two base64url strings here. Keep the private key out of version
# control, and keep the pair: browsers subscribe to the public key, so a new
# pair means every device has to subscribe again.
# VAPID_PUBLIC_KEY=
# VAPID_PRIVATE_KEY=
# Who a push service contacts about this sender: a mailto: or https: URL.
# VAPID_SUBJECT=mailto:you@example.com

# Send due reminders from the API process, checking every minute. Or leave it
# off and run one pass a minute from cron:
#   * * * * *  cd /path/to/healthMonitor/backend && uv run python -m scripts.send_reminders
# Both at once is safe: each reminder is claimed before it is sent.
# SCHEDULER_ENABLED=true
```

- [ ] **Step 4: Write the service**

Create `app/reminders/__init__.py` (empty) and `app/reminders/service.py`:

```python
"""Reminder settings, and the devices reminders are pushed to.

A reminder setting is not a table of its own. `reminder_on` sits on the profile's
`meal_slot_times` rows and is edited there in place, so the times a reminder
fires at are the diary's and the planner's, never a copy that drifts from them.

A device is a `push_subscriptions` row. It belongs to the user, not the profile,
so a profile save -- which replaces every meal-time row -- leaves it subscribed.
"""

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.profile import MealSlotTime
from app.models.push import PushSubscription
from app.models.user import User
from app.profiles import service as profiles

# The widths of the columns these land in. A User-Agent header has no length
# limit, and cutting one to fit beats a 500 from Postgres.
USER_AGENT_LENGTH = 300
TIMEZONE_LENGTH = 64


class NoProfile(LookupError):
    """No profile, so no meal times to remind about."""


class UnknownSlot(ValueError):
    """A slot that does not exist, or one switched off in the profile."""


@dataclass(frozen=True)
class SlotReminder:
    slot: str
    time: datetime.time
    # Used on Saturday and Sunday when set, as the planner does.
    weekend_time: datetime.time | None
    reminder_on: bool


def reminder_slots(db: Session, user: User) -> list[SlotReminder]:
    """The enabled slots, in meal order, with their times and reminder switch.

    A slot with no row is one the profile was saved without -- a profile from
    before meal times existed -- so it is on, at its default time, as the diary
    and the planner already treat it. A slot switched off is left out: nothing
    is eaten there on a normal day, so there is nothing to remind about.
    """
    if profiles.get_profile(db, user) is None:
        raise NoProfile
    # `get_meal_times` orders by primary key, which is a random UUID.
    rows = {row.slot: row for row in profiles.get_meal_times(db, user)}

    reminders = []
    for slot in SLOTS:
        row = rows.get(slot)
        if row is None:
            reminders.append(
                SlotReminder(slot, _default_time(slot), None, _reminder_by_default(slot))
            )
        elif row.is_enabled:
            reminders.append(SlotReminder(slot, row.usual_time, row.weekend_time, row.reminder_on))
    return reminders


def set_reminder(db: Session, user: User, slot: str, on: bool) -> None:
    """Turn one slot's reminder on or off, on the profile's own row.

    A profile saved before meal times existed has no row to edit, so one is
    created at the slot's default time -- the time it was already shown at.
    There is one row per slot (`uq_meal_time_user_slot`), so a second call
    updates the row the first created.
    """
    if profiles.get_profile(db, user) is None:
        raise NoProfile
    if slot not in SLOTS:
        raise UnknownSlot(f"Unknown slot {slot!r}")

    row = db.scalars(
        select(MealSlotTime).where(MealSlotTime.user_id == user.id, MealSlotTime.slot == slot)
    ).one_or_none()
    if row is None:
        db.add(
            MealSlotTime(
                user_id=user.id,
                slot=slot,
                usual_time=_default_time(slot),
                weekend_time=None,
                reminder_on=on,
                is_enabled=True,
            )
        )
    elif not row.is_enabled:
        # Switching a snack back on belongs to the profile, which owns the shape
        # of a normal day. A reminder switch must not quietly do it instead.
        raise UnknownSlot(f"{slot} is switched off in your profile, so it has no reminder")
    else:
        row.reminder_on = on
    db.flush()


def save_subscription(
    db: Session,
    user: User,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
    timezone: str | None,
) -> PushSubscription:
    """Store a browser's push subscription, keyed by its endpoint, for this user.

    The endpoint names one browser install. Posted again from another account,
    the row moves to that account, so a shared phone reminds only whoever
    subscribed it last. One statement rather than a read and a write: two
    posts of the same endpoint cannot both insert.

    Also records the browser's timezone on the user, when this server can
    resolve it. Nothing else writes it, and reminder times are wall-clock.
    """
    values = {
        "user_id": user.id,
        "endpoint": endpoint,
        "p256dh": p256dh,
        "auth": auth,
        "user_agent": user_agent[:USER_AGENT_LENGTH] if user_agent else None,
    }
    statement = insert(PushSubscription).values(**values)
    statement = statement.on_conflict_do_update(
        constraint="uq_push_endpoint",
        set_={name: statement.excluded[name] for name in values if name != "endpoint"},
    )
    subscription = db.scalars(
        statement.returning(PushSubscription),
        # The row may already be in this session under its previous owner. Load
        # what the statement returned over it, not what the session remembers.
        execution_options={"populate_existing": True},
    ).one()

    if timezone and _is_zone(timezone):
        user.timezone = timezone
    db.flush()
    return subscription


def delete_subscription(db: Session, user: User, endpoint: str) -> bool:
    """Forget one of this user's devices. False when the endpoint is not theirs."""
    row = db.scalars(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    ).one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def device_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == user.id)
    )


def _default_time(slot: str) -> datetime.time:
    return datetime.time.fromisoformat(DEFAULT_SLOT_TIMES[slot])


def _reminder_by_default(slot: str) -> bool:
    # The mid-morning snack is the one most often not eaten, so a reminder there
    # is opt-in: the default a profile save gives a new slot.
    return slot != "snack1"


def _is_zone(name: str) -> bool:
    """A zone this server resolves, so `local_today` never falls back to UTC on it."""
    if len(name) > TIMEZONE_LENGTH:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
```

- [ ] **Step 5: Write the router, and mount it**

Create `app/reminders/router.py`:

```python
"""Reminder settings, and the devices reminders are pushed to.

Two routers, because the settings are a screen's worth of state while the push
routes are the browser's side of a web-push subscription.
"""

import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models.user import User
from app.reminders import service

settings_router = APIRouter(prefix="/settings", tags=["settings"])
push_router = APIRouter(prefix="/push", tags=["push"])

NOT_SET_UP = "Reminders are not set up on this server"


class ReminderSlotOut(BaseModel):
    slot: str
    time: str
    weekend_time: str | None
    reminder_on: bool


class RemindersOut(BaseModel):
    slots: list[ReminderSlotOut]
    # This user's subscribed browsers. Whether the one asking is among them, and
    # whether it may show notifications at all, are facts only that browser has.
    devices: int


class ReminderIn(BaseModel):
    slot: str
    reminder_on: bool


class PublicKeyOut(BaseModel):
    key: str


class PushKeysIn(BaseModel):
    # The widths of the columns they are stored in.
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class SubscriptionIn(BaseModel):
    """What the browser's `PushSubscription.toJSON()` gives, plus its timezone.

    `expirationTime` is ignored; browsers leave it null.
    """

    # The server POSTs to this URL. A push service is always https, and refusing
    # anything else closes the easiest way to aim the server's requests at a
    # plain-http service on its own network.
    endpoint: str = Field(max_length=2048, pattern=r"^https://")
    keys: PushKeysIn
    # The browser's IANA zone. One this server cannot resolve is ignored rather
    # than refused: the subscription is still good.
    timezone: str | None = None


class DevicesOut(BaseModel):
    devices: int


class UnsubscribeIn(BaseModel):
    endpoint: str


def _hhmm(value: datetime.time) -> str:
    return value.strftime("%H:%M")


def _out(db: Session, user: User) -> RemindersOut:
    return RemindersOut(
        slots=[
            ReminderSlotOut(
                slot=item.slot,
                time=_hhmm(item.time),
                weekend_time=_hhmm(item.weekend_time) if item.weekend_time else None,
                reminder_on=item.reminder_on,
            )
            for item in service.reminder_slots(db, user)
        ],
        devices=service.device_count(db, user),
    )


@settings_router.get("/reminders", response_model=RemindersOut)
def read_reminders(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RemindersOut:
    try:
        return _out(db, user)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


@settings_router.patch("/reminders", response_model=RemindersOut)
def update_reminder(
    payload: ReminderIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemindersOut:
    try:
        service.set_reminder(db, user, payload.slot, payload.reminder_on)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    except service.UnknownSlot as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return _out(db, user)


@push_router.get(
    "/public-key", response_model=PublicKeyOut, dependencies=[Depends(get_current_user)]
)
def read_public_key() -> PublicKeyOut:
    # Both halves, not only the one handed out: a browser subscribed to a key the
    # server cannot sign with would wait for reminders that never come.
    if not (settings.vapid_public_key and settings.vapid_private_key):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)
    return PublicKeyOut(key=settings.vapid_public_key)


@push_router.post("/subscriptions", response_model=DevicesOut, status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: SubscriptionIn,
    user_agent: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DevicesOut:
    service.save_subscription(
        db,
        user,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=user_agent,
        timezone=payload.timezone,
    )
    db.commit()
    return DevicesOut(devices=service.device_count(db, user))


@push_router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: UnsubscribeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Another user's endpoint is as unknown as a made-up one: which devices
    # someone else has is not this caller's to find out.
    if not service.delete_subscription(db, user, payload.endpoint):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such device")
    db.commit()
```

In `app/main.py`:
- add `from app.reminders.router import push_router, settings_router` directly after the `app.profiles.router` import. It sorts before the `app.reports.router` import that Task 5 added.
- add these two lines after the last `app.include_router(...)` line:
```python
app.include_router(settings_router)
app.include_router(push_router)
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_reminders_api.py tests/test_tracking_api.py tests/test_auth_api.py tests/test_push_models.py -q && uv run ruff check .`
Expected: all PASS (41 in `test_reminders_api.py`), and ruff clean. The profile and sign-in suites are unaffected, because nothing on their path changed. `test_a_profile_save_keeps_a_reminder_turned_off_here` passes only with Task 9 in place. If it fails, check that `save_profile` still reads the previous rows before deleting them.

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/main.py app/reminders .env.example tests/test_reminders_api.py
git commit -m "feat(backend): serve reminder settings and push subscriptions over HTTP

GET and PATCH /settings/reminders read and switch reminder_on on the
profile's own meal-time rows. A reminder therefore fires at the time the
diary shows and the planner plans for, and there is no second copy of the
times to drift. Slots come back in meal order, not the rows' random key
order. A profile saved before meal times existed reminds at the default
times, and the first switch creates that slot's row. A snack switched off in
the profile has no reminder to set, because turning a meal back on is the
profile's job.

POST /push/subscriptions upserts by endpoint in one statement. An endpoint
names a browser, so a shared phone subscribed from a second account moves to
that account and reminds only its current user. The same call records the
browser's timezone, the only thing that writes it, since reminder times are
wall-clock. A zone the server cannot resolve is ignored rather than failing
a good subscription. Only https endpoints are accepted, because the server
will POST to them. GET /push/public-key answers 503 until both VAPID keys
are set, so the screen can say reminders are not set up here instead of
subscribing a browser that nothing will ever reach.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Deciding and sending reminders

This task makes the reminders real. A pure schedule decides which slots are due. A channel delivers them. A runner joins the two, and claims each reminder in `reminder_deliveries` before it sends anything, so a reminder goes at most once. A slot is due for the hour after its time, by the user's own wall clock. It must have its reminder on, and the diary must have nothing for it: no food and no skip, since a skip is an explicit "not eating this". Web push is the first channel, through `pywebpush`. The loop runs inside the API only when `SCHEDULER_ENABLED` is set, and a one-shot script serves an external cron. Nothing here adds HTTP. Task 10 put the settings and subscriptions behind routes, and Task 12 gives the browser its push handler.

**Files:**
- Create: `app/reminders/schedule.py` (pure), `app/reminders/channels.py`, `app/reminders/runner.py`, `scripts/send_reminders.py`
- Modify:
  - `pyproject.toml`, `uv.lock`: `uv add pywebpush`
  - `app/local_time.py`: `local_now`
  - `app/main.py`: the lifespan
  - `tests/conftest.py`: the loop forced off for the whole suite
- Test: `tests/test_reminder_schedule.py` (create, pure), `tests/test_reminder_runner.py` (create), `tests/test_webpush_channel.py` (create), `tests/test_local_time.py` (extend)

**Interfaces:**
- Consumes:
  - Task 3: `PushSubscription`; `ReminderDelivery` and its `uq_delivery_user_day_slot` key. A claim goes in as `failed` and is corrected once the channel answers, as Task 3's model comment says.
  - Task 5: `app.diary.service.slot_states(db, user, on_date) -> dict[str, str]`, where each slot is `logged`, `skipped` or `empty`.
  - Task 10: `SlotReminder` and `reminder_slots(db, user)` from `app.reminders.service`; the settings `vapid_private_key`, `vapid_subject` and `scheduler_enabled`; and `PATCH /settings/reminders`, in one test only.
- Produces:
```python
# app/local_time.py
def local_now(user: User, now_utc: datetime.datetime) -> datetime.datetime
    # aware, in the user's zone (UTC when theirs is bad); ValueError on a naive now_utc

# app/reminders/schedule.py  -- pure
LATE_LIMIT = datetime.timedelta(minutes=60)
SLOT_TITLES = {"breakfast": "Breakfast", "snack1": "Mid-morning snack", "lunch": "Lunch",
               "snack2": "Evening snack", "dinner": "Dinner"}
def slot_time_on(reminder: SlotReminder, day: datetime.date) -> datetime.time
def due_slots(local_now: datetime.datetime, reminders: Sequence[SlotReminder],
              accounted: frozenset[str]) -> list[str]            # SLOTS order
@dataclass(frozen=True)
class Reminder:
    slot: str; local_date: datetime.date; title: str; body: str; url: str; tag: str
def reminder_for(slot: str, day: datetime.date) -> Reminder

# app/reminders/channels.py
class Channel(Protocol):
    def send(self, db: Session, user: User, reminder: Reminder) -> str  # sent | failed | no-device
class WebPushChannel:
    TTL_SECONDS = 45 * 60
    def __init__(self, private_key: str, subject: str) -> None
# The push payload, which Task 12's public/push-handlers.js reads:
#   {"title": str, "body": str, "url": "/log?slot=<slot>", "tag": "<slot>-<YYYY-MM-DD>"}

# app/reminders/runner.py
def tick(db: Session, now_utc: datetime.datetime, channel: Channel) -> int   # reminders sent
def run_once(channel: Channel) -> int              # one tick in its own SessionLocal, committed
async def run_forever(interval_seconds: int = 60) -> None

# app/main.py
app = FastAPI(..., lifespan=lifespan)   # runs run_forever() only with SCHEDULER_ENABLED and a key
```

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_local_time.py` with the version below. The two existing tests are unchanged apart from a shared `user_in` helper, and four tests for `local_now` follow them:

```python
"""A user's date and wall clock are theirs, not the server's, and a garbage zone breaks neither."""

import datetime
import zoneinfo

import pytest

from app.local_time import local_now, local_today
from app.models.user import User

# 02:40 UTC is 08:10 in Kolkata, five and a half hours ahead.
INSTANT = datetime.datetime(2026, 8, 17, 2, 40, tzinfo=datetime.UTC)


def user_in(zone: str) -> User:
    return User(google_sub="s", email="e@example.com", name="n", timezone=zone)


def test_today_is_the_date_where_the_user_is():
    user = user_in("Asia/Kolkata")
    assert local_today(user) == datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()


def test_an_unknown_timezone_falls_back_to_utc():
    user = user_in("Not/AZone")
    assert local_today(user) == datetime.datetime.now(datetime.UTC).date()


def test_now_is_the_users_wall_clock():
    local = local_now(user_in("Asia/Kolkata"), INSTANT)

    assert (local.date(), local.hour, local.minute) == (datetime.date(2026, 8, 17), 8, 10)
    # The same instant, read in their zone.
    assert local == INSTANT


def test_the_users_date_can_be_a_day_ahead_of_utc():
    # 20:00 UTC on the 16th is 01:30 on the 17th in Kolkata.
    evening = datetime.datetime(2026, 8, 16, 20, 0, tzinfo=datetime.UTC)
    assert local_now(user_in("Asia/Kolkata"), evening).date() == datetime.date(2026, 8, 17)


def test_an_unknown_timezone_reads_the_clock_in_utc():
    local = local_now(user_in("Not/AZone"), INSTANT)
    assert (local.hour, local.minute, local.utcoffset()) == (2, 40, datetime.timedelta(0))


def test_a_naive_instant_is_refused():
    # A naive value would be read as the server's local time, which is wrong on any
    # server that is not set to UTC.
    with pytest.raises(ValueError, match="timezone-aware"):
        local_now(user_in("Asia/Kolkata"), INSTANT.replace(tzinfo=None))
```

Create `tests/test_reminder_schedule.py`:

```python
"""When a meal reminder is due. Pure, and on fixed dates.

A slot is due for an hour from its time, by the user's wall clock and on their
date. Its weekend time applies on Saturday and Sunday. It is never due once the
meal is logged or skipped, or while its reminder is off. 17 August 2026 is a
Monday, and the 22nd and 23rd are the weekend after it.
"""

import datetime
from zoneinfo import ZoneInfo

import pytest

from app.meal_slots import SLOTS
from app.reminders.schedule import (
    LATE_LIMIT,
    SLOT_TITLES,
    Reminder,
    due_slots,
    reminder_for,
    slot_time_on,
)
from app.reminders.service import SlotReminder

KOLKATA = ZoneInfo("Asia/Kolkata")
MONDAY = datetime.date(2026, 8, 17)
SATURDAY = datetime.date(2026, 8, 22)
SUNDAY = datetime.date(2026, 8, 23)

NOTHING: frozenset[str] = frozenset()


def meal(
    slot: str,
    hour: int,
    minute: int = 0,
    weekend: datetime.time | None = None,
    on: bool = True,
) -> SlotReminder:
    return SlotReminder(
        slot=slot, time=datetime.time(hour, minute), weekend_time=weekend, reminder_on=on
    )


def clock(day: datetime.date, hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """A moment on the user's wall clock in Kolkata."""
    return datetime.datetime.combine(day, datetime.time(hour, minute, second), tzinfo=KOLKATA)


BREAKFAST = meal("breakfast", 8, weekend=datetime.time(9, 30))


def test_the_late_limit_is_an_hour():
    assert LATE_LIMIT == datetime.timedelta(minutes=60)


@pytest.mark.parametrize(
    ("hour", "minute", "second", "due"),
    [
        (7, 59, 59, False),  # not yet
        (8, 0, 0, True),  # from the slot's time
        (8, 59, 59, True),  # through the hour after it
        (9, 0, 0, False),  # an hour late sends nothing rather than a stale nudge
    ],
)
def test_a_slot_is_due_for_the_hour_from_its_time(hour, minute, second, due):
    now = clock(MONDAY, hour, minute, second)
    assert due_slots(now, [BREAKFAST], NOTHING) == (["breakfast"] if due else [])


def test_a_slot_whose_reminder_is_off_is_never_due():
    snack = meal("snack1", 11, on=False)
    assert due_slots(clock(MONDAY, 11, 10), [snack], NOTHING) == []


def test_a_slot_the_diary_accounts_for_is_not_due():
    # The runner passes logged and skipped slots alike.
    assert due_slots(clock(MONDAY, 8, 10), [BREAKFAST], frozenset({"breakfast"})) == []


def test_another_slot_being_accounted_for_does_not_hide_this_one():
    assert due_slots(clock(MONDAY, 8, 10), [BREAKFAST], frozenset({"lunch"})) == ["breakfast"]


def test_due_slots_come_in_meal_order():
    early_lunch = meal("lunch", 11, 30)
    snack = meal("snack1", 11)
    now = clock(MONDAY, 11, 40)
    assert due_slots(now, [early_lunch, snack], NOTHING) == ["snack1", "lunch"]


@pytest.mark.parametrize("day", [SATURDAY, SUNDAY])
def test_the_weekend_time_applies_on_saturday_and_sunday(day):
    assert slot_time_on(BREAKFAST, day) == datetime.time(9, 30)
    assert due_slots(clock(day, 8, 10), [BREAKFAST], NOTHING) == []
    assert due_slots(clock(day, 9, 40), [BREAKFAST], NOTHING) == ["breakfast"]


def test_a_weekday_keeps_the_usual_time():
    assert slot_time_on(BREAKFAST, MONDAY) == datetime.time(8, 0)
    assert due_slots(clock(MONDAY, 9, 40), [BREAKFAST], NOTHING) == []


def test_a_weekend_without_its_own_time_keeps_the_usual_one():
    assert slot_time_on(meal("lunch", 13, 30), SUNDAY) == datetime.time(13, 30)


def test_a_late_dinner_is_not_reminded_on_the_next_day():
    dinner = meal("dinner", 23, 30)
    assert due_slots(clock(MONDAY, 23, 50), [dinner], NOTHING) == ["dinner"]
    # 00:10 on Tuesday is 40 minutes after Monday's dinner, but on another date.
    # Tuesday's own dinner is nearly a day away, and Monday's diary is not Tuesday's.
    tuesday = MONDAY + datetime.timedelta(days=1)
    assert due_slots(clock(tuesday, 0, 10), [dinner], NOTHING) == []


def test_the_reminder_names_the_meal_and_links_to_logging_it():
    assert reminder_for("snack1", MONDAY) == Reminder(
        slot="snack1",
        local_date=MONDAY,
        title="Mid-morning snack",
        body="Nothing logged for mid-morning snack yet. Tap to log it.",
        url="/log?slot=snack1",
        tag="snack1-2026-08-17",
    )


def test_every_slot_has_a_title():
    assert set(SLOT_TITLES) == set(SLOTS)
```

Create `tests/test_reminder_runner.py`:

```python
"""The runner: the due slots of subscribed users, each claimed once, then sent.

The channel here is a fake that records what it was handed. These tests cover
the deciding and the claiming; test_webpush_channel.py covers the delivery.

Every tick is at a fixed time on the real today in Kolkata. A profile save
records a weigh-in dated today, so the day must be the real one. A fixed time of
day keeps the tests clear of midnight and of the edges of a slot's hour. PROFILE
puts breakfast at 08:00, and saves the mid-morning snack's reminder off.
"""

import asyncio
import datetime
import zoneinfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main
from app.config import settings
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User
from app.reminders import runner
from app.reminders.channels import WebPushChannel
from app.reminders.schedule import Reminder, reminder_for
from scripts import send_reminders
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def at(hour: int, minute: int, zone: datetime.tzinfo = KOLKATA) -> datetime.datetime:
    """A time on today's wall clock in `zone`, as the UTC instant the runner takes."""
    local = datetime.datetime.combine(TODAY, datetime.time(hour, minute), tzinfo=zone)
    return local.astimezone(datetime.UTC)


class FakeChannel:
    """Records every reminder it is handed, and answers `outcome`."""

    def __init__(self, outcome: str = "sent") -> None:
        self.outcome = outcome
        self.sent: list[tuple[str, Reminder]] = []

    def send(self, db, user: User, reminder: Reminder) -> str:
        self.sent.append((user.email, reminder))
        return self.outcome


class BrokenChannel:
    def send(self, db, user: User, reminder: Reminder) -> str:
        raise RuntimeError("the push library fell over")


def subscribe(db, user: User) -> None:
    db.add(
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example.com/{user.google_sub}",
            p256dh="p" * 87,
            auth="a" * 22,
        )
    )
    db.flush()


def deliveries(db, user: User) -> list[tuple[str, datetime.date, str]]:
    rows = db.scalars(
        select(ReminderDelivery)
        .where(ReminderDelivery.user_id == user.id)
        .order_by(ReminderDelivery.local_date, ReminderDelivery.slot)
    )
    return [(row.slot, row.local_date, row.status) for row in rows]


def log_food(api, dish, slot: str) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(TODAY),
            "slot": slot,
            "food_id": str(dish.id),
            "food_kind": "dish",
            "grams": 150,
            "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    """The signed-in user, with a profile and one subscribed device."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    found = db.scalar(select(User).where(User.email == "track@example.com"))
    subscribe(db, found)
    return found


def test_a_due_slot_with_nothing_logged_is_reminded(db, user):
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 1

    assert channel.sent == [("track@example.com", reminder_for("breakfast", TODAY))]
    assert deliveries(db, user) == [("breakfast", TODAY, "sent")]


def test_a_reminder_goes_once_however_often_the_runner_ticks(db, user):
    channel = FakeChannel()
    runner.tick(db, at(8, 10), channel)

    assert runner.tick(db, at(8, 11), channel) == 0
    assert runner.tick(db, at(8, 55), channel) == 0
    assert len(channel.sent) == 1


def test_a_reminder_another_runner_claimed_is_not_sent_again(db, user):
    """An overlapping cron run, a second instance, or a tick from before a restart."""
    db.add(ReminderDelivery(user_id=user.id, local_date=TODAY, slot="breakfast", status="sent"))
    db.flush()
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_yesterdays_reminder_does_not_count_for_today(db, user):
    yesterday = TODAY - datetime.timedelta(days=1)
    db.add(ReminderDelivery(user_id=user.id, local_date=yesterday, slot="breakfast", status="sent"))
    db.flush()

    assert runner.tick(db, at(8, 10), FakeChannel()) == 1


def test_a_logged_slot_is_not_reminded(db, user, signed_in, reference_data):
    log_food(signed_in, reference_data, "breakfast")
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    # Nothing was claimed either: the reminder was never due.
    assert deliveries(db, user) == []


def test_food_in_another_slot_does_not_account_for_this_one(db, user, signed_in, reference_data):
    log_food(signed_in, reference_data, "lunch")
    assert runner.tick(db, at(8, 10), FakeChannel()) == 1


def test_a_skipped_slot_is_not_reminded(db, user, signed_in):
    skipped = signed_in.post("/diary/skips", json={"date": str(TODAY), "slot": "breakfast"})
    assert skipped.status_code == 201
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_a_reminder_turned_off_in_settings_is_not_sent(db, user, signed_in):
    turned_off = signed_in.patch(
        "/settings/reminders", json={"slot": "breakfast", "reminder_on": False}
    )
    assert turned_off.status_code == 200
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_a_slot_saved_with_its_reminder_off_is_not_sent(db, user):
    # 11:10 is ten minutes into the mid-morning snack, which PROFILE saves with its
    # reminder off. No other slot is due then.
    channel = FakeChannel()
    assert runner.tick(db, at(11, 10), channel) == 0
    assert channel.sent == []


def test_a_tick_more_than_an_hour_late_sends_nothing(db, user):
    # The runner was down from before 08:00 until 09:05: breakfast's hour is over.
    channel = FakeChannel()

    assert runner.tick(db, at(9, 5), channel) == 0
    assert channel.sent == []
    assert deliveries(db, user) == []


def test_the_slot_time_is_the_users_own_wall_clock(db, user):
    user.timezone = "UTC"
    db.flush()
    channel = FakeChannel()

    # 08:10 in Kolkata is 02:40 in UTC, hours before this user's breakfast.
    assert runner.tick(db, at(8, 10), channel) == 0
    assert runner.tick(db, at(8, 10, datetime.UTC), channel) == 1
    assert [reminder.local_date for _, reminder in channel.sent] == [TODAY]


def test_a_user_with_no_device_is_not_considered(db, signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    user = db.scalar(select(User).where(User.email == "track@example.com"))
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    assert deliveries(db, user) == []


def test_a_device_with_no_profile_behind_it_is_passed_over(db):
    stranger = User(google_sub="sub-stranger", email="stranger@example.com", name="Stranger")
    db.add(stranger)
    db.flush()
    subscribe(db, stranger)
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    assert deliveries(db, stranger) == []


@pytest.mark.parametrize("outcome", ["failed", "no-device"])
def test_the_channels_answer_is_recorded_and_not_retried(db, user, outcome):
    channel = FakeChannel(outcome)

    assert runner.tick(db, at(8, 10), channel) == 0
    assert runner.tick(db, at(8, 11), channel) == 0

    assert len(channel.sent) == 1
    assert deliveries(db, user) == [("breakfast", TODAY, outcome)]


def test_a_channel_that_raises_is_recorded_as_a_failure(db, user):
    assert runner.tick(db, at(8, 10), BrokenChannel()) == 0
    assert deliveries(db, user) == [("breakfast", TODAY, "failed")]


class Stop(BaseException):
    """Ends run_forever from inside a tick. `except Exception` must let it through."""


def test_the_loop_ticks_again_after_a_failed_tick(monkeypatch):
    channels = []

    def fake_run_once(channel) -> int:
        channels.append(channel)
        if len(channels) == 1:
            raise RuntimeError("the database is restarting")
        if len(channels) == 3:
            raise Stop
        return 0

    monkeypatch.setattr(runner, "run_once", fake_run_once)

    with pytest.raises(Stop):
        asyncio.run(runner.run_forever(interval_seconds=0))

    assert len(channels) == 3
    assert all(isinstance(channel, WebPushChannel) for channel in channels)


def recording_loop(events: list[str]):
    """A stand-in for run_forever that records when it starts and when it stops."""

    async def fake_run_forever(interval_seconds: int = 60) -> None:
        events.append("started")
        try:
            await asyncio.Event().wait()
        finally:
            events.append("stopped")

    return fake_run_forever


def test_the_api_runs_the_loop_when_enabled_and_stops_it_on_shutdown(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "vapid_private_key", "a-private-key")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert events == ["started"]

    assert events == ["started", "stopped"]


def test_the_suite_keeps_the_loop_off(monkeypatch):
    """conftest turns SCHEDULER_ENABLED off, so a key alone starts nothing."""
    events: list[str] = []
    monkeypatch.setattr(settings, "vapid_private_key", "a-private-key")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

    assert events == []


def test_the_loop_needs_a_key_to_sign_with(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "vapid_private_key", "")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

    assert events == []


def test_the_cron_script_needs_a_key(monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", "")
    assert send_reminders.main() == 1
```

Create `tests/test_webpush_channel.py`:

```python
"""Web push goes to every device the user subscribed, signed for each push service.
A device the push service has forgotten is forgotten here too.

`pywebpush.webpush` is replaced by a fake. It behaves like the real one in the
two ways that matter here. It writes the endpoint's origin into the claims dict
it is handed, and it raises WebPushException carrying the push service's
response.
"""

import datetime
import json
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import pywebpush
import requests
from sqlalchemy import select

from app.models.push import PushSubscription
from app.models.user import User
from app.reminders.channels import WebPushChannel
from app.reminders.schedule import reminder_for

DAY = datetime.date(2026, 8, 17)
PHONE = "https://fcm.googleapis.com/fcm/send/phone-token"
LAPTOP = "https://updates.push.services.mozilla.com/wpush/v2/laptop-token"
PRIVATE_KEY = "vapid-private-key"
SUBJECT = "mailto:reminders@example.com"


class FakePushService:
    """Stands in for pywebpush.webpush. Records each push, and refuses the endpoints
    in `refusals`."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.refusals: dict[str, Exception] = {}

    def __call__(self, **kwargs) -> SimpleNamespace:
        endpoint = kwargs["subscription_info"]["endpoint"]
        claims = kwargs["vapid_claims"]
        # What the real webpush does to the claims it is handed.
        if not claims.get("aud"):
            origin = urlparse(endpoint)
            claims["aud"] = f"{origin.scheme}://{origin.netloc}"
        self.calls.append({**kwargs, "vapid_claims": dict(claims)})
        if endpoint in self.refusals:
            raise self.refusals[endpoint]
        return SimpleNamespace(status_code=201)

    def endpoints(self) -> set[str]:
        return {call["subscription_info"]["endpoint"] for call in self.calls}


@pytest.fixture
def push_service(monkeypatch) -> FakePushService:
    fake = FakePushService()
    monkeypatch.setattr(pywebpush, "webpush", fake)
    return fake


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def user(db) -> User:
    return make_user(db, "push")


def subscribe(db, user: User, endpoint: str) -> None:
    token = endpoint.rsplit("/", 1)[-1]
    db.add(
        PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh=f"p256dh-{token}", auth=f"auth-{token}"
        )
    )
    db.flush()


def endpoints(db, user: User) -> set[str]:
    return set(
        db.scalars(select(PushSubscription.endpoint).where(PushSubscription.user_id == user.id))
    )


def send(db, user: User) -> str:
    return WebPushChannel(PRIVATE_KEY, SUBJECT).send(db, user, reminder_for("lunch", DAY))


def refusal(status: int) -> pywebpush.WebPushException:
    return pywebpush.WebPushException(
        f"Push failed: {status}", response=SimpleNamespace(status_code=status)
    )


def test_a_reminder_goes_to_every_device_the_user_subscribed(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)

    assert send(db, user) == "sent"
    assert push_service.endpoints() == {PHONE, LAPTOP}


def test_the_push_carries_what_the_notification_shows(db, user, push_service):
    subscribe(db, user, PHONE)
    send(db, user)

    [call] = push_service.calls
    assert json.loads(call["data"]) == {
        "title": "Lunch",
        "body": "Nothing logged for lunch yet. Tap to log it.",
        "url": "/log?slot=lunch",
        "tag": "lunch-2026-08-17",
    }
    assert call["subscription_info"] == {
        "endpoint": PHONE,
        "keys": {"p256dh": "p256dh-phone-token", "auth": "auth-phone-token"},
    }
    assert call["vapid_private_key"] == PRIVATE_KEY
    assert call["vapid_claims"]["sub"] == SUBJECT
    # 45 minutes: a reminder that arrives later is about a meal already eaten.
    assert call["ttl"] == 2700


def test_each_push_is_signed_for_its_own_push_service(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    send(db, user)

    audiences = {
        call["subscription_info"]["endpoint"]: call["vapid_claims"]["aud"]
        for call in push_service.calls
    }
    assert audiences == {
        PHONE: "https://fcm.googleapis.com",
        LAPTOP: "https://updates.push.services.mozilla.com",
    }


@pytest.mark.parametrize("status", [404, 410])
def test_a_device_the_push_service_has_forgotten_is_forgotten(db, user, push_service, status):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    push_service.refusals[PHONE] = refusal(status)

    assert send(db, user) == "sent"
    assert endpoints(db, user) == {LAPTOP}


def test_a_refusal_for_any_other_reason_keeps_the_device(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = refusal(500)

    assert send(db, user) == "failed"
    assert endpoints(db, user) == {PHONE}


def test_an_unreachable_push_service_is_a_failure_not_a_crash(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = requests.ConnectionError("push service unreachable")

    assert send(db, user) == "failed"
    assert endpoints(db, user) == {PHONE}


@pytest.mark.parametrize(
    "error",
    [ValueError("Unsupported elliptic curve point type"), IndexError("index out of range")],
)
def test_keys_that_cannot_be_encrypted_to_fail_only_that_device(db, user, push_service, error):
    # The subscribe route checks only the keys' length, and pywebpush raises a plain
    # ValueError or IndexError for keys that are not a base64url P-256 point.
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    push_service.refusals[PHONE] = error

    assert send(db, user) == "sent"
    assert push_service.endpoints() == {PHONE, LAPTOP}
    assert endpoints(db, user) == {PHONE, LAPTOP}


def test_when_every_device_is_gone_there_is_no_device(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = refusal(410)

    assert send(db, user) == "no-device"
    assert endpoints(db, user) == set()


def test_a_user_with_no_device_is_not_pushed(db, user, push_service):
    assert send(db, user) == "no-device"
    assert push_service.calls == []


def test_only_the_users_own_devices_are_pushed(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, make_user(db, "other"), LAPTOP)

    send(db, user)

    assert push_service.endpoints() == {PHONE}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_local_time.py tests/test_reminder_schedule.py tests/test_reminder_runner.py tests/test_webpush_channel.py -q`
Expected: FAIL, with 4 errors during collection:
- `ImportError: cannot import name 'local_now' from 'app.local_time'`
- `ModuleNotFoundError: No module named 'app.reminders.schedule'`
- `ImportError: cannot import name 'runner' from 'app.reminders'`
- `ModuleNotFoundError: No module named 'pywebpush'`

- [ ] **Step 3: Add pywebpush**

Run: `uv add pywebpush`

This adds `pywebpush` to `[project] dependencies` in `pyproject.toml`, and updates `uv.lock`. It brings `py-vapid`, which signs the VAPID token, and `http-ece`, which encrypts the payload to the browser's keys. Check that it imports:

Run: `uv run python -c "import pywebpush; print(pywebpush.webpush, pywebpush.WebPushException)"`
Expected: the function and the exception class, with no error.

- [ ] **Step 4: The user's wall clock**

Replace `app/local_time.py` with:

```python
"""The user's date and wall clock. A day boundary is theirs, not the server's."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown name, or one malformed enough to be rejected outright. A bad
        # stored timezone should not break the request; UTC is a defensible last
        # resort, and clients pass dates explicitly for most reads anyway.
        return ZoneInfo("UTC")


def local_today(user: User) -> datetime.date:
    return datetime.datetime.now(tz=_zone(user)).date()


def local_now(user: User, now_utc: datetime.datetime) -> datetime.datetime:
    """The instant `now_utc` on the user's wall clock: aware, in their zone.

    It takes the instant rather than reading the clock, so one reminder tick
    decides every user at the same moment, and its tests can choose that moment.
    """
    if now_utc.tzinfo is None:
        # astimezone() would read a naive value as the server's own local time.
        raise ValueError("now_utc must be timezone-aware")
    return now_utc.astimezone(_zone(user))
```

`local_today` keeps its behaviour, and the zone fallback now lives in `_zone`, which both functions share.

- [ ] **Step 5: The schedule**

Create `app/reminders/schedule.py`:

```python
"""Which meal reminders are due. Pure: no database and no clock.

A slot is due for an hour from its time, by the user's wall clock and on their
date. It is due only if its reminder is on and the diary does not already
account for it. A logged slot needs no nudge. A skipped slot is an explicit "not
eating this", so nagging after it would be wrong.

The hour is also the limit on lateness. A runner that was down at 08:00 and
comes back at 09:05 sends nothing for breakfast. By then the reminder would be
about a meal already eaten, or already missed.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from app.meal_slots import SLOTS
from app.planner.rules import sunday_index
from app.reminders.service import SlotReminder

LATE_LIMIT = datetime.timedelta(minutes=60)

SLOT_TITLES = {
    "breakfast": "Breakfast",
    "snack1": "Mid-morning snack",
    "lunch": "Lunch",
    "snack2": "Evening snack",
    "dinner": "Dinner",
}


@dataclass(frozen=True)
class Reminder:
    """One notification, as the channel sends it and the service worker shows it."""

    slot: str
    local_date: datetime.date
    title: str
    body: str
    # Where a tap on the notification opens.
    url: str
    # One notification per slot and day. A second push with the same tag replaces
    # the first on the device rather than stacking beside it.
    tag: str


def slot_time_on(reminder: SlotReminder, day: datetime.date) -> datetime.time:
    """The slot's time on `day`: its weekend time on Saturday and Sunday, when it has one.

    This is the planner's rule, so a reminder and the plan agree on when a meal is.
    """
    if sunday_index(day) in (0, 6) and reminder.weekend_time is not None:
        return reminder.weekend_time
    return reminder.time


def due_slots(
    local_now: datetime.datetime,
    reminders: Sequence[SlotReminder],
    accounted: frozenset[str],
) -> list[str]:
    """The slots to remind about at `local_now`, in meal order.

    `accounted` holds the slots the diary already has an answer for, logged or
    skipped. Only the slot on `local_now`'s own date counts, so a 23:30 dinner is
    not reminded at 00:10: that is another day, with its own diary.
    """
    day = local_now.date()
    due = set()
    for reminder in reminders:
        if not reminder.reminder_on or reminder.slot in accounted:
            continue
        # The same tzinfo as `local_now`, so the comparison is on the wall clock.
        start = datetime.datetime.combine(day, slot_time_on(reminder, day), tzinfo=local_now.tzinfo)
        if start <= local_now < start + LATE_LIMIT:
            due.add(reminder.slot)
    return [slot for slot in SLOTS if slot in due]


def reminder_for(slot: str, day: datetime.date) -> Reminder:
    title = SLOT_TITLES[slot]
    return Reminder(
        slot=slot,
        local_date=day,
        title=title,
        body=f"Nothing logged for {title.lower()} yet. Tap to log it.",
        url=f"/log?slot={slot}",
        tag=f"{slot}-{day.isoformat()}",
    )
```

- [ ] **Step 6: The channel, and web push**

Create `app/reminders/channels.py`:

```python
"""Where a reminder goes. A channel delivers one reminder to one user.

The runner decides what is due and claims it. A channel only delivers, and
answers "sent", "failed" or "no-device", which the runner records on the claim.
Web push is the first channel. Another one, such as an email or a WhatsApp
message, would be another class with the same `send`, and the runner would not
change.
"""

import json
import logging
from typing import Protocol

import pywebpush
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.push import PushSubscription
from app.models.user import User
from app.reminders.schedule import Reminder

logger = logging.getLogger(__name__)

# What a push service answers for a subscription that no longer exists. The user
# revoked the permission or cleared the site's data, or the browser moved to a new
# endpoint. RFC 8030 says to stop sending to it, and a row left behind would fail
# again at every meal.
GONE_STATUSES = frozenset({404, 410})

# How long to wait on one push service. The tick sends to every user in turn, so
# one hung push service must not hold up everyone after it.
PUSH_TIMEOUT_SECONDS = 10


class Channel(Protocol):
    def send(self, db: Session, user: User, reminder: Reminder) -> str:
        """Deliver `reminder` to `user`, and answer "sent", "failed" or "no-device"."""


class WebPushChannel:
    """Browser push, signed with the server's VAPID key (RFC 8292)."""

    # How long a push service holds the reminder for a phone that is off or offline.
    # A slot is claimed within a minute of its time, so this lapses before the
    # slot's hour is over. A reminder that arrives later than that is about a meal
    # already eaten, and it is better dropped.
    TTL_SECONDS = 45 * 60

    def __init__(self, private_key: str, subject: str) -> None:
        self._private_key = private_key
        self._subject = subject

    def send(self, db: Session, user: User, reminder: Reminder) -> str:
        """Push to every device the user subscribed. "sent" when any of them took it."""
        subscriptions = list(
            db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id))
        )
        if not subscriptions:
            return "no-device"

        # The service worker shows exactly this. It never stays silent, because
        # Chrome penalises a push that shows nothing and Safari can revoke it.
        payload = json.dumps(
            {
                "title": reminder.title,
                "body": reminder.body,
                "url": reminder.url,
                "tag": reminder.tag,
            }
        )
        outcomes = [self._push(subscription, payload) for subscription in subscriptions]
        for subscription, outcome in zip(subscriptions, outcomes, strict=True):
            if outcome == "gone":
                db.delete(subscription)
        db.flush()

        if "sent" in outcomes:
            return "sent"
        if all(outcome == "gone" for outcome in outcomes):
            return "no-device"
        return "failed"

    def _push(self, subscription: PushSubscription, payload: str) -> str:
        """Push to one device: "sent", "gone" (the push service forgot it) or "failed"."""
        try:
            pywebpush.webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=self._private_key,
                # A new dict for every push. webpush writes the endpoint's origin into
                # the dict as the token's audience. A dict reused across devices would
                # sign the second push for the first device's push service, and the
                # second push service would refuse it.
                vapid_claims={"sub": self._subject},
                ttl=self.TTL_SECONDS,
                timeout=PUSH_TIMEOUT_SECONDS,
            )
        except pywebpush.WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in GONE_STATUSES:
                return "gone"
            logger.warning("web push refused with status %s", status)
            return "failed"
        except requests.RequestException:
            logger.warning("web push could not reach the push service", exc_info=True)
            return "failed"
        except (ValueError, IndexError):
            # Keys no browser would send, which the subscribe route lets through
            # because it checks only their length: one that is not base64url, or
            # not a point on P-256. A VAPID private key that does not parse lands
            # here too. This device fails and the user's other devices are still
            # pushed. It is not "gone": a bad server key must not delete every
            # subscription.
            logger.warning("web push could not encrypt or sign for this device", exc_info=True)
            return "failed"
        return "sent"
```

- [ ] **Step 7: The runner**

Create `app/reminders/runner.py`:

```python
"""The reminder runner. It works out what is due, claims it once, and sends it.

`tick` is one pass at one instant. It takes every user who has a subscribed
device and a profile, reads their wall clock and their meal times, and asks the
schedule which slots are due. It drops the slots the diary already accounts for,
logged or skipped.

Each remaining reminder is claimed with INSERT ... ON CONFLICT DO NOTHING
RETURNING before anything is sent, and only the tick that gets the row back
sends it. The unique key on (user, local date, slot) is the whole of "exactly
once". An earlier tick, an overlapping cron run and a second instance all lose
that insert, so nothing has to remember what already went out.

A claim goes in as failed and is then set to the channel's answer. A reminder
is never retried: for a nudge, at most once is the right side to err on.

`run_forever` is the loop the API's lifespan starts. `scripts.send_reminders`
runs one tick for an external cron. Each commits after its tick, and both may
run at the same time.
"""

import asyncio
import datetime
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.diary import service as diary
from app.local_time import local_now
from app.models.profile import Profile
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User
from app.reminders import service as reminders
from app.reminders.channels import Channel, WebPushChannel
from app.reminders.schedule import Reminder, due_slots, reminder_for

logger = logging.getLogger(__name__)


def tick(db: Session, now_utc: datetime.datetime, channel: Channel) -> int:
    """Send every reminder due at `now_utc` that has not gone yet. Returns how many were sent."""
    sent = 0
    for user in _reminded_users(db):
        local = local_now(user, now_utc)
        day = local.date()
        times = reminders.reminder_slots(db, user)
        # Most ticks find nothing due for anyone, so the clock rules a user out
        # before their diary is read.
        if not due_slots(local, times, frozenset()):
            continue
        states = diary.slot_states(db, user, day)
        accounted = frozenset(slot for slot, state in states.items() if state != "empty")

        for slot in due_slots(local, times, accounted):
            claim = _claim(db, user, day, slot)
            if claim is None:
                # Claimed already, by an earlier tick, a cron run or another instance.
                continue
            # The claim is made durable BEFORE anything is sent: a crash after the send
            # can then never send it again. At most once is the right failure mode for
            # a nudge -- a missed reminder costs less than a duplicate. This is the one
            # place outside a router that commits; the runner is the job's entry point.
            db.commit()
            outcome = _deliver(db, user, reminder_for(slot, day), channel)
            db.execute(
                update(ReminderDelivery).where(ReminderDelivery.id == claim).values(status=outcome)
            )
            db.commit()
            if outcome == "sent":
                sent += 1
    return sent


def run_once(channel: Channel) -> int:
    """One tick at the current instant, in its own session, committed."""
    with SessionLocal() as db:
        sent = tick(db, datetime.datetime.now(datetime.UTC), channel)
        db.commit()
    return sent


async def run_forever(interval_seconds: int = 60) -> None:
    """Tick every `interval_seconds` until cancelled. The API's lifespan runs this."""
    channel = WebPushChannel(settings.vapid_private_key, settings.vapid_subject)
    while True:
        try:
            # The backend is sync: the session, psycopg and pywebpush's requests.
            # So the tick runs in a worker thread, off the loop that serves the API.
            await asyncio.to_thread(run_once, channel)
        except Exception:
            # A database restart or a network blip costs one tick, not the loop.
            # Every claim is committed before its send, so a failed tick sends
            # nothing twice; a reminder it had not claimed yet is decided again
            # by the next tick within the slot's hour.
            logger.exception("reminder tick failed")
        await asyncio.sleep(interval_seconds)


def _reminded_users(db: Session) -> list[User]:
    """Users with a subscribed device and a profile, in id order.

    A device with no profile behind it has no meals to remind about. The fixed
    order makes two runners claim in the same order, so neither can hold a claim
    the other needs while it waits on one of the other's.
    """
    has_device = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    has_profile = select(Profile.id).where(Profile.user_id == User.id).exists()
    return list(db.scalars(select(User).where(has_device, has_profile).order_by(User.id)))


def _claim(db: Session, user: User, day: datetime.date, slot: str) -> uuid.UUID | None:
    """Claim one reminder. Returns the new row's id, or None when it was claimed already."""
    return db.execute(
        insert(ReminderDelivery)
        .values(user_id=user.id, local_date=day, slot=slot, status="failed")
        .on_conflict_do_nothing(constraint="uq_delivery_user_day_slot")
        .returning(ReminderDelivery.id)
    ).scalar_one_or_none()


def _deliver(db: Session, user: User, reminder: Reminder, channel: Channel) -> str:
    """The channel's answer, or "failed" when the channel raised."""
    try:
        return channel.send(db, user, reminder)
    except Exception:
        # One user's failed send must not end the tick for everyone after them.
        # The claim is already committed as failed, and stays failed: a reminder
        # is never retried.
        logger.exception("sending the %s reminder failed", reminder.tag)
        return "failed"
```

- [ ] **Step 8: Start the loop in the lifespan, and keep it out of the suite**

In `app/main.py`:

1. Replace the first line, `from fastapi import FastAPI`, with:
   ```python
   import asyncio
   import contextlib
   import logging
   from collections.abc import AsyncIterator

   from fastapi import FastAPI
   ```
2. Add `from app.reminders.runner import run_forever` directly after the `from app.reminders.router import ...` line that Task 10 added. `router` sorts before `runner`, and both sort before Task 5's `app.reports.router`.
3. Replace `app = FastAPI(title="healthMonitor API")` with:

```python
logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the reminder loop beside the API, on the instance configured to send them.

    Off unless SCHEDULER_ENABLED is set. Every TestClient runs this lifespan, and
    the loop opens its own sessions on the development database's engine, not the
    test's. The loop signs pushes with the VAPID private key, so without one it
    would only record every reminder as failed.
    """
    task = None
    if settings.scheduler_enabled and settings.vapid_private_key:
        task = asyncio.create_task(run_forever())
    elif settings.scheduler_enabled:
        logger.warning("SCHEDULER_ENABLED is set without VAPID_PRIVATE_KEY: no reminders")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="healthMonitor API", lifespan=lifespan)
```

In `tests/conftest.py`, add this fixture directly above `@pytest.fixture(scope="session")` / `def engine():`. `pytest` and `settings` are already imported there.

```python
@pytest.fixture(scope="session", autouse=True)
def scheduler_off():
    """Keep the reminder loop out of the suite, whatever `.env` says.

    Every TestClient runs the app's lifespan, which starts the loop when
    SCHEDULER_ENABLED is set. The loop opens its own sessions on the development
    database, outside the test's rolled-back transaction. Under the suite it
    would send real pushes, from development data, to devices subscribed there.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "scheduler_enabled", False)
        yield
```

The flag already defaults to false, but `Settings` reads `.env`. A developer who turns the scheduler on there to try reminders by hand would otherwise start it under every API test.

- [ ] **Step 9: One tick for cron**

Create `scripts/send_reminders.py`:

```python
"""Send the meal reminders due now, once each, and exit. This is the reminder loop for cron.

The API can run the reminders itself, with SCHEDULER_ENABLED=true. A deployment
that would rather keep them out of the web process runs this every minute:

    * * * * *  cd /path/to/backend && uv run python -m scripts.send_reminders

Running both is safe. Each reminder is claimed in the database before it is
sent, and only the runner that claims it sends it.

Usage:
    uv run python -m scripts.send_reminders
"""

import sys

from app.config import settings
from app.reminders.channels import WebPushChannel
from app.reminders.runner import run_once


def main() -> int:
    if not settings.vapid_private_key:
        print(
            "VAPID_PRIVATE_KEY is not set, so there is no key to sign a push with.",
            file=sys.stderr,
        )
        return 1
    sent = run_once(WebPushChannel(settings.vapid_private_key, settings.vapid_subject))
    print(f"reminders sent: {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10: Run the tests**

Run: `uv run pytest tests/test_local_time.py tests/test_reminder_schedule.py tests/test_reminder_runner.py tests/test_webpush_channel.py tests/test_reminders_api.py tests/test_push_models.py tests/test_health.py -q && uv run ruff check .`
Expected: all PASS, ruff clean. `test_health.py` runs the lifespan through the `client` fixture, with the loop held off by the new session fixture.

Then check the script's entry point without a key. An empty variable overrides `.env`, so nothing touches a database:

Run: `VAPID_PRIVATE_KEY= uv run python -m scripts.send_reminders; echo "exit $?"`
Expected: `VAPID_PRIVATE_KEY is not set, so there is no key to sign a push with.` then `exit 1`.

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml uv.lock app/local_time.py app/main.py app/reminders/schedule.py \
  app/reminders/channels.py app/reminders/runner.py scripts/send_reminders.py \
  tests/conftest.py tests/test_local_time.py tests/test_reminder_schedule.py \
  tests/test_reminder_runner.py tests/test_webpush_channel.py
git commit -m "feat(backend): send meal reminders by web push, each at most once

A slot is due for the hour after its time, on the user's own wall clock, with
its weekend time on Saturday and Sunday. It must have its reminder on, and
the diary must have nothing for it: no food, and no skip, because a skip is
an explicit 'not eating this'. A tick more than an hour late sends nothing,
rather than a nudge about a meal already eaten.

Each reminder is claimed in reminder_deliveries with INSERT ... ON CONFLICT
DO NOTHING RETURNING before it is sent. An earlier tick, an overlapping cron
run or a second instance loses the insert instead of sending again. The
claim records what the channel answered, and is never retried.

Delivery sits behind a Channel protocol, and web push is the first adapter.
It pushes to every device of the user, with a new VAPID claims dict for each
push, because webpush writes the audience into the dict it is given. A 404
or 410 deletes the subscription the push service has forgotten.

The loop starts in the API's lifespan only with SCHEDULER_ENABLED and a VAPID
key set. Every TestClient runs the lifespan against the development database,
so conftest forces it off. scripts.send_reminders runs one tick for cron.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Frontend — reminders on the real endpoints, and push on this device

This task puts the Reminders screen on Task 10's endpoints and lets a browser receive what Task 11 sends. The switches are the profile's own `reminder_on`, read and set through `/settings/reminders`. The PATCH answers with the whole settings, so the screen shows what was saved, and a failed switch stays as it was. Push itself belongs to one browser. Whether this browser can take reminders, and whether it has allowed notifications, are facts only the browser has, so the screen asks it (`usePush.ts`) and not the server. That is why `push_granted` leaves the contract. A browser subscribes from a tap, because the permission prompt needs a user gesture, and only under the production worker `/sw.js`, because that worker carries the push handler; in dev, MSW's worker owns the scope. The handler is a plain-JS file in `public/`, and `workbox.importScripts` loads it into the generated worker, which stays `generateSW`. Signing out unsubscribes this browser first, while the session still exists, so a shared phone stops reminding the person who left it.

**Files:**
- Create:
  - `public/push-handlers.js`
  - `src/settings/usePush.ts` (feature detection, subscribe and unsubscribe)
  - `src/settings/useReminders.ts`
  - `src/mocks/pushApis.ts` (test stand-ins for the service worker container, PushManager and Notification; nothing in the app imports it)
  - `src/settings/usePush.test.ts`, `src/settings/pushHandlers.test.ts`
- Modify:
  - `vite.config.ts` (`workbox.importScripts: ['push-handlers.js']`)
  - `src/settings/types.ts`
  - `src/settings/RemindersScreen.tsx`
  - `src/settings/RemindersScreen.test.tsx`
  - `src/auth/useSession.ts` (sign-out unsubscribes this device first; plan 7's cache clearing stays)
  - `src/auth/useSession.test.tsx` (plan 7's three sign-in/sign-out cache tests stay; three push tests are added)
  - `src/mocks/fixtures/more.ts` (`REMINDERS_FIXTURE`)
  - `src/mocks/handlers/index.ts` (the reminders handlers are deleted, leaving no plan handlers)

**Interfaces:**
- Consumes:
  - Task 10's HTTP contract. `GET /settings/reminders` answers `{slots: [{slot, time, weekend_time, reminder_on}], devices}` in meal order, or 404 without a profile. `PATCH /settings/reminders {slot, reminder_on}` answers the same shape. `GET /push/public-key` answers `{key}`, or 503 "Reminders are not set up on this server". `POST /push/subscriptions {endpoint, keys: {p256dh, auth}, timezone?}` answers 201 `{devices}`. `DELETE /push/subscriptions {endpoint}` answers 204, or 404 when the endpoint is not this user's.
  - Task 11's push payload, the JSON `{title, body, url: "/log?slot=<slot>", tag: "<slot>-<YYYY-MM-DD>"}`.
  - Task 9: the wizard invalidates `['settings', 'reminders']` after a save, and sends every slot's `reminder_on` back from the cached `['profile']` (`SavedProfile.meal_times`).
  - Task 8's version of `src/mocks/handlers/index.ts`, which holds demo auth and the two reminders handlers.
- Produces:
```ts
// src/settings/types.ts -- the Task 10 contract
export interface MealTimeSetting {
  slot: MealSlot; time: string; weekend_time: string | null; reminder_on: boolean
}
export interface ReminderSettings { slots: MealTimeSetting[]; devices: number }
export interface ReminderChange { slot: MealSlot; reminder_on: boolean }   // PATCH body
export interface PushPublicKey { key: string }
export interface NewPushSubscription {
  endpoint: string; keys: { p256dh: string; auth: string }; timezone?: string
}
export interface PushDevices { devices: number }
export interface PushUnsubscribe { endpoint: string }                     // DELETE body

// src/settings/usePush.ts
export type PushSupport = 'unsupported' | 'needs-install' | 'dev-worker' | 'ready'
export type DeviceState = 'blocked' | 'on' | 'off'
export function pushSupport(): Promise<PushSupport>   // ready only under the production /sw.js
export function thisDevice(): Promise<DeviceState>
export async function subscribeThisDevice(): Promise<void>
    // requestPermission -> GET key -> subscribe -> POST (with the Intl timezone)
export async function unsubscribeThisDevice(): Promise<void>   // unsubscribe + DELETE; never throws
export function usePushSupport()        // ['push', 'support']
export function usePushKey()            // ['push', 'key']
export function useThisDevice()         // ['push', 'device']
export function useTurnOnThisDevice()   // mutation: subscribeThisDevice
export function useTurnOffThisDevice()  // mutation: unsubscribeThisDevice

// src/settings/useReminders.ts
export function useReminders()     // ['settings', 'reminders']
export function useSetReminder()   // PATCH; the answer replaces that cache and patches ['profile']

// public/push-handlers.js: push -> showNotification(title, {body, tag, icon, data: {url}});
//   notificationclick -> close, then focus and navigate an open window, or open one
```

- [ ] **Step 1: Write the contract as built**

Replace `src/settings/types.ts`:

```ts
import type { MealSlot } from '../log/types'

/**
 * CONTRACT for `GET /settings/reminders`, `PATCH /settings/reminders` and the
 * `/push` routes — plan 8.
 *
 * Amended from the plan 2.5 proposal. `push_granted` is gone: whether a browser
 * may show notifications is a fact about that one browser, which it reads for
 * itself (`usePush.ts`). In its place is the number of this user's subscribed
 * devices. The times themselves are the profile's, and are edited there.
 */
export interface MealTimeSetting {
  slot: MealSlot
  /** Usual weekday time, "HH:MM". */
  time: string
  /** Saturday and Sunday, when it differs — a Sunday breakfast rarely happens at 8am. */
  weekend_time: string | null
  /**
   * Whether to remind at this slot. The optional mid-morning snack is off by
   * default, so it does not nag someone who rarely eats it.
   */
  reminder_on: boolean
}

export interface ReminderSettings {
  /** The slots enabled in the profile, in meal order. A switched-off snack is left out. */
  slots: MealTimeSetting[]
  /** This user's browsers subscribed to push, on every device they use. */
  devices: number
}

/** `PATCH /settings/reminders` body. It answers with the whole `ReminderSettings`. */
export interface ReminderChange {
  slot: MealSlot
  reminder_on: boolean
}

/**
 * `GET /push/public-key`. Answers 503 "Reminders are not set up on this server"
 * until the server has its VAPID key pair.
 */
export interface PushPublicKey {
  key: string
}

/**
 * `POST /push/subscriptions` body: the browser's subscription, and its IANA
 * timezone, which is the only thing that sets the user's. It answers 201
 * `PushDevices`.
 */
export interface NewPushSubscription {
  endpoint: string
  keys: { p256dh: string; auth: string }
  timezone?: string
}

export interface PushDevices {
  devices: number
}

/**
 * `DELETE /push/subscriptions` body. It answers 204, or 404 when the endpoint is
 * not this user's.
 */
export interface PushUnsubscribe {
  endpoint: string
}
```

In `src/mocks/fixtures/more.ts`, `REMINDERS_FIXTURE` follows the contract: delete its `push_granted: false,` line, and add `devices: 0,` after the closing `],` of `slots`. It then reads:

```ts
export const REMINDERS_FIXTURE: ReminderSettings = {
  slots: [
    { slot: 'breakfast', time: '08:00', weekend_time: '09:30', reminder_on: true },
    { slot: 'snack1', time: '11:00', weekend_time: null, reminder_on: false },
    { slot: 'lunch', time: '13:30', weekend_time: '14:00', reminder_on: true },
    { slot: 'snack2', time: '17:00', weekend_time: null, reminder_on: true },
    { slot: 'dinner', time: '20:30', weekend_time: null, reminder_on: true },
  ],
  devices: 0,
}
```

Replace `src/mocks/handlers/index.ts`. The two reminders handlers and the `REMINDERS_FIXTURE` import go, which leaves demo auth alone:

```ts
import type { RequestHandler } from 'msw'
import { demoAuthHandlers } from './demoAuth'

/**
 * Handlers for endpoints the backend has NOT built yet. There are none left.
 *
 * Every endpoint the app calls exists in FastAPI now, the weekly report and the
 * reminders last, in plan 8. So in dev every request falls through to the real
 * server (`onUnhandledRequest: 'bypass'`), and in Vitest each test stubs what it
 * calls with `server.use(...)`.
 *
 * Demo auth is all that remains. It is opt-in, so the default set never shadows
 * a real endpoint.
 */
export const handlers: RequestHandler[] = [
  ...(import.meta.env.VITE_DEMO_AUTH === 'true' ? demoAuthHandlers : []),
]
```

- [ ] **Step 2: Write the failing tests**

jsdom has no service worker, no PushManager and no Notification, which is a browser with no push at all. Create `src/mocks/pushApis.ts`, the stand-ins three test files share:

```ts
import { vi } from 'vitest'

/**
 * Stand-ins for the browser's push APIs, which jsdom does not have: the service
 * worker container, PushManager and Notification. Test support only; nothing in
 * the app imports this file.
 *
 * `installPush` puts them in place for one test, and `pretendToBe` changes what
 * the browser says it is. Call `uninstallPush` from `afterEach` to take both away
 * again, so the next test starts as jsdom does: a browser with no push at all.
 */

export const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/this-device'
export const P256DH = 'B' + 'p'.repeat(86)
export const AUTH = 'a'.repeat(22)

export const PRODUCTION_WORKER = 'http://localhost:3000/sw.js'
export const MOCK_WORKER = 'http://localhost:3000/mockServiceWorker.js'

export const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
/** iPadOS asks for desktop sites, so its Safari says it is a Mac. */
export const IPAD_SAFARI =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/18.5 Safari/605.1.15'

interface PushOptions {
  /** The script of the page's worker, or null when no worker is registered at all. */
  worker?: string | null
  /** The worker is still installing, as on a first visit. */
  installing?: boolean
  permission?: NotificationPermission
  /** What the permission prompt answers. */
  answer?: NotificationPermission
  /** This browser is already subscribed. */
  subscribed?: boolean
}

function fakeSubscription(onUnsubscribe: () => void) {
  return {
    endpoint: ENDPOINT,
    toJSON: (): PushSubscriptionJSON => ({
      endpoint: ENDPOINT,
      expirationTime: null,
      keys: { p256dh: P256DH, auth: AUTH },
    }),
    unsubscribe: vi.fn(async () => {
      onUnsubscribe()
      return true
    }),
  }
}

export function installPush({
  worker = PRODUCTION_WORKER,
  installing = false,
  permission = 'default',
  answer = 'granted',
  subscribed = false,
}: PushOptions = {}) {
  let current: ReturnType<typeof fakeSubscription> | null = null
  const subscription = fakeSubscription(() => {
    current = null
  })
  if (subscribed) current = subscription

  const pushManager = {
    getSubscription: vi.fn(async () => current),
    subscribe: vi.fn(async (_options: PushSubscriptionOptionsInit) => {
      current = subscription
      return subscription
    }),
  }
  const script = worker === null ? null : { scriptURL: worker }
  const registration =
    script === null
      ? undefined
      : {
          active: installing ? null : script,
          waiting: null,
          installing: installing ? script : null,
          pushManager,
        }
  const container = {
    getRegistration: vi.fn(async () => registration),
    // With no worker it never settles, as in a real browser.
    ready: registration === undefined ? new Promise(() => {}) : Promise.resolve(registration),
  }
  Object.defineProperty(navigator, 'serviceWorker', { value: container, configurable: true })

  const notification = {
    permission,
    requestPermission: vi.fn(async () => {
      notification.permission = answer
      return answer
    }),
  }
  vi.stubGlobal('Notification', notification)
  vi.stubGlobal('PushManager', class PushManager {})

  return { container, pushManager, subscription, notification }
}

export function pretendToBe(
  userAgent: string,
  { standalone, maxTouchPoints }: { standalone?: boolean; maxTouchPoints?: number } = {},
) {
  Object.defineProperty(navigator, 'userAgent', { value: userAgent, configurable: true })
  if (standalone !== undefined) {
    Object.defineProperty(navigator, 'standalone', { value: standalone, configurable: true })
  }
  if (maxTouchPoints !== undefined) {
    Object.defineProperty(navigator, 'maxTouchPoints', {
      value: maxTouchPoints,
      configurable: true,
    })
  }
}

export function uninstallPush() {
  // Own properties only: jsdom's own userAgent, on the prototype, shows through again.
  for (const name of ['serviceWorker', 'userAgent', 'standalone', 'maxTouchPoints']) {
    Reflect.deleteProperty(navigator, name)
  }
  vi.unstubAllGlobals()
}
```

Create `src/settings/usePush.test.ts`. The key `AQID-_8` is unpadded base64url and uses both characters that plain base64 spells differently (`-` for `+` and `_` for `/`). It decodes to the bytes `[1, 2, 3, 251, 255]`:

```ts
import { http, HttpResponse } from 'msw'
import { afterEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import {
  AUTH,
  ENDPOINT,
  IPAD_SAFARI,
  IPHONE_SAFARI,
  MOCK_WORKER,
  P256DH,
  installPush,
  pretendToBe,
  uninstallPush,
} from '../mocks/pushApis'
import { server } from '../mocks/server'
import { pushSupport, subscribeThisDevice, thisDevice, unsubscribeThisDevice } from './usePush'

// Base64url, unpadded, with both of the characters plain base64 spells differently.
const KEY = 'AQID-_8'
const KEY_BYTES = [1, 2, 3, 251, 255]

afterEach(() => uninstallPush())

function serveKey(events: string[] = []) {
  server.use(
    http.get(apiUrl('/push/public-key'), () => {
      events.push('key')
      return HttpResponse.json({ key: KEY })
    }),
  )
}

// --- what this browser can do ---------------------------------------------------------

test('a browser without push cannot take reminders', async () => {
  expect(await pushSupport()).toBe('unsupported')
})

test('a browser missing only notifications cannot take reminders', async () => {
  installPush()
  vi.stubGlobal('Notification', undefined)

  expect(await pushSupport()).toBe('unsupported')
})

// iOS delivers web push only to an app on the home screen, and until then Safari
// has none of the APIs. Reading that as "unsupported" would hide the one fix.
test('Safari on an iPhone must add the app to the home screen first', async () => {
  pretendToBe(IPHONE_SAFARI)

  expect(await pushSupport()).toBe('needs-install')
})

test('an iPad that says it is a Mac is still an iPad', async () => {
  pretendToBe(IPAD_SAFARI, { maxTouchPoints: 5 })

  expect(await pushSupport()).toBe('needs-install')
})

test('a Mac is not an iPad', async () => {
  pretendToBe(IPAD_SAFARI, { maxTouchPoints: 0 })
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('the app on an iPhone home screen can take reminders', async () => {
  pretendToBe(IPHONE_SAFARI)
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(display-mode: standalone)',
  }))
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('older iOS says it is on the home screen through navigator.standalone', async () => {
  pretendToBe(IPHONE_SAFARI, { standalone: true })
  installPush()

  expect(await pushSupport()).toBe('ready')
})

// In dev, MSW's worker owns the scope and has no push handler.
test('a page the mock worker controls cannot subscribe', async () => {
  installPush({ worker: MOCK_WORKER })

  expect(await pushSupport()).toBe('dev-worker')
})

// `ready` never settles here, so waiting on it would hang the screen.
test('a page with no worker at all is told so, without waiting for one', async () => {
  installPush({ worker: null })

  expect(await pushSupport()).toBe('dev-worker')
})

test('the production worker can take reminders', async () => {
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('the production worker counts while it is still installing', async () => {
  installPush({ installing: true })

  expect(await pushSupport()).toBe('ready')
})

test('a browser that refuses to look up its worker cannot take reminders', async () => {
  const push = installPush()
  push.container.getRegistration.mockRejectedValue(new DOMException('denied', 'SecurityError'))

  expect(await pushSupport()).toBe('unsupported')
})

// --- where this device stands ---------------------------------------------------------

test('a device that denied notifications is blocked', async () => {
  installPush({ permission: 'denied' })

  expect(await thisDevice()).toBe('blocked')
})

test('a permitted, subscribed device is on', async () => {
  installPush({ permission: 'granted', subscribed: true })

  expect(await thisDevice()).toBe('on')
})

// After signing out, the permission stays but the subscription is gone. Reading
// that as "on" would leave the next person with no way to turn reminders on.
test('a permitted device with no subscription is off', async () => {
  installPush({ permission: 'granted' })

  expect(await thisDevice()).toBe('off')
})

// --- turning reminders on -------------------------------------------------------------

test('asks first, then subscribes with the server’s key, and registers the device', async () => {
  const events: string[] = []
  const push = installPush()
  push.notification.requestPermission.mockImplementation(async () => {
    events.push('permission')
    push.notification.permission = 'granted'
    return 'granted'
  })
  push.pushManager.subscribe.mockImplementation(async () => {
    events.push('subscribe')
    return push.subscription
  })
  serveKey(events)
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      events.push('register')
      posted = await request.json()
      return HttpResponse.json({ devices: 1 }, { status: 201 })
    }),
  )

  await subscribeThisDevice()

  // The prompt comes first: Safari shows it only from inside the tap.
  expect(events).toEqual(['permission', 'key', 'subscribe', 'register'])
  const [options] = push.pushManager.subscribe.mock.calls[0]
  expect(options.userVisibleOnly).toBe(true)
  expect(Array.from(options.applicationServerKey as Uint8Array)).toEqual(KEY_BYTES)
  expect(posted).toEqual({
    endpoint: ENDPOINT,
    keys: { p256dh: P256DH, auth: AUTH },
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  })
})

test('a refused prompt subscribes nothing, and is not an error', async () => {
  const events: string[] = []
  const push = installPush({ answer: 'denied' })
  serveKey(events)

  await expect(subscribeThisDevice()).resolves.toBeUndefined()

  expect(events).toEqual([])
  expect(push.pushManager.subscribe).not.toHaveBeenCalled()
})

test('a server without push keys says so, and nothing is subscribed', async () => {
  const push = installPush()
  server.use(
    http.get(
      apiUrl('/push/public-key'),
      () => new HttpResponse('Reminders are not set up on this server', { status: 503 }),
    ),
  )

  await expect(subscribeThisDevice()).rejects.toMatchObject({ status: 503 })
  expect(push.pushManager.subscribe).not.toHaveBeenCalled()
})

// Left subscribed, the browser would read as "on" while the server never reminds it.
test('a device the server could not store is not left subscribed', async () => {
  const push = installPush()
  serveKey()
  server.use(
    http.post(apiUrl('/push/subscriptions'), () => new HttpResponse('boom', { status: 500 })),
  )

  await expect(subscribeThisDevice()).rejects.toMatchObject({ status: 500 })
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(await thisDevice()).toBe('off')
})

// --- turning reminders off ------------------------------------------------------------

test('turning off unsubscribes the browser and forgets the device on the server', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  let forgotten: unknown = null
  server.use(
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      forgotten = await request.json()
      return new HttpResponse(null, { status: 204 })
    }),
  )

  await unsubscribeThisDevice()

  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(forgotten).toEqual({ endpoint: ENDPOINT })
})

test('with nothing subscribed, nothing is sent', async () => {
  installPush({ permission: 'granted' })
  const deleted = vi.fn()
  server.use(
    http.delete(apiUrl('/push/subscriptions'), () => {
      deleted()
      return new HttpResponse(null, { status: 204 })
    }),
  )

  await unsubscribeThisDevice()

  expect(deleted).not.toHaveBeenCalled()
})

test('a server that cannot forget the device still leaves the browser unsubscribed', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  server.use(
    http.delete(apiUrl('/push/subscriptions'), () => new HttpResponse('boom', { status: 500 })),
  )

  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
})

test('turning off never throws, whatever the browser does', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  push.container.getRegistration.mockRejectedValue(new DOMException('denied', 'SecurityError'))

  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
})

test('turning off in a browser without push does nothing', async () => {
  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
})
```

`public/push-handlers.js` runs inside the service worker, which jsdom does not have. It touches nothing but `self`, so the test runs its source against a stand-in for the worker's global scope and dispatches the events by hand. Create `src/settings/pushHandlers.test.ts`:

```ts
import { expect, test, vi } from 'vitest'
import source from '../../public/push-handlers.js?raw'

/*
 * public/push-handlers.js runs inside the service worker, which jsdom does not
 * have. It touches nothing but `self`, so it is run here against a stand-in for
 * the worker's global scope, and its events are dispatched by hand.
 */

const ORIGIN = 'https://nutrients.example'

// What Task 11's WebPushChannel sends for lunch on 17 August.
const LUNCH = {
  title: 'Lunch',
  body: 'Nothing logged for lunch yet. Tap to log it.',
  url: '/log?slot=lunch',
  tag: 'lunch-2026-08-17',
}

/** A window of this app that the worker controls. */
function windowClient() {
  return {
    url: `${ORIGIN}/`,
    focus: vi.fn(async () => undefined),
    navigate: vi.fn(async (_url: string) => undefined),
  }
}

function worker(windows: ReturnType<typeof windowClient>[] = []) {
  const listeners = new Map<string, (event: object) => void>()
  const scope = {
    location: new URL(`${ORIGIN}/sw.js`),
    registration: { showNotification: vi.fn(async (_title: string, _options: object) => {}) },
    clients: {
      matchAll: vi.fn(async (_options: object) => windows),
      openWindow: vi.fn(async (_url: string) => null),
    },
    addEventListener: (type: string, listener: (event: object) => void) => {
      listeners.set(type, listener)
    },
  }
  new Function('self', source)(scope)

  /** Dispatch one event, and wait for everything it asked the worker to wait for. */
  async function dispatch(type: string, event: object) {
    const pending: Promise<unknown>[] = []
    listeners.get(type)?.({ ...event, waitUntil: (work: Promise<unknown>) => pending.push(work) })
    await Promise.all(pending)
  }

  return { scope, dispatch }
}

function push(payload: unknown) {
  return { data: { json: () => payload } }
}

function click(url: unknown) {
  return { notification: { data: { url }, close: vi.fn() } }
}

test('a push shows exactly what the server sent', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', push(LUNCH))

  expect(scope.registration.showNotification).toHaveBeenCalledWith('Lunch', {
    body: 'Nothing logged for lunch yet. Tap to log it.',
    tag: 'lunch-2026-08-17',
    icon: '/icon-192.png',
    data: { url: '/log?slot=lunch' },
  })
})

// A push that shows nothing gets a generic notification on Chrome, and Safari
// can revoke the subscription for it.
test('a push it cannot read still shows a notification', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', {
    data: {
      json: () => {
        throw new SyntaxError('Unexpected token')
      },
    },
  })

  expect(scope.registration.showNotification).toHaveBeenCalledWith('Nutrient Tracker', {
    body: 'Time to log your meal.',
    icon: '/icon-192.png',
    data: { url: '/log' },
  })
})

test('a push with no payload still shows a notification', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', { data: null })

  expect(scope.registration.showNotification).toHaveBeenCalledWith(
    'Nutrient Tracker',
    expect.objectContaining({ body: 'Time to log your meal.' }),
  )
})

test('a tap brings an open window to the slot’s logging screen', async () => {
  const open = windowClient()
  const { scope, dispatch } = worker([open])
  const event = click('/log?slot=lunch')

  await dispatch('notificationclick', event)

  expect(event.notification.close).toHaveBeenCalledOnce()
  expect(scope.clients.matchAll).toHaveBeenCalledWith({ type: 'window' })
  expect(open.focus).toHaveBeenCalledOnce()
  expect(open.navigate).toHaveBeenCalledWith(`${ORIGIN}/log?slot=lunch`)
  expect(scope.clients.openWindow).not.toHaveBeenCalled()
})

test('with no window open, a tap opens one at the slot', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', click('/log?slot=dinner'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log?slot=dinner`)
})

test('a window that cannot be navigated gives way to a new one', async () => {
  const stuck = windowClient()
  stuck.navigate.mockRejectedValue(new TypeError('This service worker is not the client’s'))
  const { scope, dispatch } = worker([stuck])

  await dispatch('notificationclick', click('/log?slot=lunch'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log?slot=lunch`)
})

// The payload comes only from this app's server, but a notification is never
// a way off the app.
test('a link to another site opens the Log screen instead', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', click('https://elsewhere.example/log'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log`)
})

test('a notification with no link opens the Log screen', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', { notification: { data: null, close: vi.fn() } })

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log`)
})
```

Replace `src/settings/RemindersScreen.test.tsx`. The four original assertions stay: the switch names (`Breakfast · 08:00`, `Dinner · 20:30`), the snack switch off, the PATCH body `{slot, reminder_on}`, and the iPhone home-screen hint. The hint now appears for an iPhone rather than for a missing `push_granted`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { REMINDERS_FIXTURE } from '../mocks/fixtures/more'
import {
  ENDPOINT,
  IPHONE_SAFARI,
  MOCK_WORKER,
  installPush,
  pretendToBe,
  uninstallPush,
} from '../mocks/pushApis'
import { server } from '../mocks/server'
import type { SavedProfile } from '../onboarding/useProfile'
import { RemindersScreen } from './RemindersScreen'
import type { ReminderSettings } from './types'

const TURN_ON = { name: 'Turn on reminders on this device' }

let devices = 0

beforeEach(() => {
  devices = 0
  server.use(
    http.get(apiUrl('/settings/reminders'), () =>
      HttpResponse.json<ReminderSettings>({ ...REMINDERS_FIXTURE, devices }),
    ),
  )
})

afterEach(() => uninstallPush())

function serveKey() {
  server.use(http.get(apiUrl('/push/public-key'), () => HttpResponse.json({ key: 'AQID-_8' })))
}

/** The PATCH answers as the server does after dinner's switch: the whole settings. */
function serveDinnerOff(patched: (body: unknown) => void = () => {}) {
  server.use(
    http.patch(apiUrl('/settings/reminders'), async ({ request }) => {
      patched(await request.json())
      return HttpResponse.json<ReminderSettings>({
        ...REMINDERS_FIXTURE,
        slots: REMINDERS_FIXTURE.slots.map((slot) =>
          slot.slot === 'dinner' ? { ...slot, reminder_on: false } : slot,
        ),
      })
    }),
  )
}

function newQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderScreen(queryClient = newQueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RemindersScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function cachedDinner(queryClient: QueryClient) {
  return queryClient
    .getQueryData<SavedProfile>(['profile'])
    ?.meal_times.find((item) => item.slot === 'dinner')
}

// --- the slots --------------------------------------------------------------------------

test('lists every meal slot with its usual time', async () => {
  renderScreen()

  expect(await screen.findByRole('switch', { name: /breakfast · 08:00/i })).toBeInTheDocument()
  expect(await screen.findByRole('switch', { name: /dinner · 20:30/i })).toBeInTheDocument()
  expect(screen.getByText('Weekends at 09:30')).toBeInTheDocument()
})

// The optional mid-morning snack must not nag someone who rarely eats it.
test('shows the optional snack reminder as off', async () => {
  renderScreen()

  expect(
    await screen.findByRole('switch', { name: /mid-morning snack/i }),
  ).not.toBeChecked()
})

test('turning a slot’s reminder off sends just that slot', async () => {
  const patched = vi.fn()
  serveDinnerOff(patched)
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  await userEvent.click(dinner)

  await waitFor(() =>
    expect(patched).toHaveBeenCalledWith({ slot: 'dinner', reminder_on: false }),
  )
  // The answer is the saved state, and the switch shows it.
  await waitFor(() => expect(dinner).not.toBeChecked())
})

test('a reminder that could not be changed says so, and stays as it was', async () => {
  server.use(
    http.patch(apiUrl('/settings/reminders'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  await userEvent.click(dinner)

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be changed/)
  expect(dinner).toBeChecked()
})

// The answer replaces every switch, so an earlier answer landing late would undo a later one.
test('the switches wait for the last change before taking another', async () => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.patch(apiUrl('/settings/reminders'), async () => {
      await held
      return HttpResponse.json<ReminderSettings>(REMINDERS_FIXTURE)
    }),
  )
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  const breakfast = screen.getByRole('switch', { name: /breakfast/i })
  await userEvent.click(dinner)

  await waitFor(() => expect(breakfast).toBeDisabled())
  release()
  await waitFor(() => expect(breakfast).toBeEnabled())
})

// The profile form sends every slot's reminder back with a save, from the profile
// it last read. Left stale, that copy would switch this reminder back on.
test('a switch changed here is what the profile form sends next', async () => {
  serveDinnerOff()
  const queryClient = newQueryClient()
  queryClient.setQueryData(['profile'], {
    meal_times: REMINDERS_FIXTURE.slots.map((slot) => ({ ...slot, is_enabled: true })),
  })
  renderScreen(queryClient)

  await userEvent.click(await screen.findByRole('switch', { name: /dinner/i }))

  await waitFor(() => expect(cachedDinner(queryClient)?.reminder_on).toBe(false))
  expect(queryClient.getQueryData<SavedProfile>(['profile'])?.meal_times).toHaveLength(5)
})

test('a profile saved before meal times existed gains the row the switch created', async () => {
  serveDinnerOff()
  const queryClient = newQueryClient()
  queryClient.setQueryData(['profile'], { meal_times: [] })
  renderScreen(queryClient)

  await userEvent.click(await screen.findByRole('switch', { name: /dinner/i }))

  await waitFor(() =>
    expect(cachedDinner(queryClient)).toEqual({
      slot: 'dinner',
      time: '20:30',
      weekend_time: null,
      reminder_on: false,
      is_enabled: true,
    }),
  )
})

test('sends a user with no profile to set one up rather than showing an error', async () => {
  server.use(
    http.get(apiUrl('/settings/reminders'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// --- this device ------------------------------------------------------------------------

// iOS only delivers web push to a PWA installed on the home screen, which is a
// real constraint the user has to be told about rather than left to discover.
test('explains the iPhone install requirement before offering anything', async () => {
  pretendToBe(IPHONE_SAFARI)
  renderScreen()

  expect(await screen.findByText(/add this app to your home screen/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('a browser without push is told so, and offered nothing', async () => {
  renderScreen()

  expect(await screen.findByText('This browser can’t show reminders')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

// In dev, MSW's worker owns the page and has no push handler.
test('a page the mock worker controls offers nothing', async () => {
  installPush({ worker: MOCK_WORKER })
  renderScreen()

  expect(
    await screen.findByText('Reminders can’t be turned on from this page'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('says so when the server is not set up to send reminders', async () => {
  installPush()
  server.use(
    http.get(
      apiUrl('/push/public-key'),
      () => new HttpResponse('Reminders are not set up on this server', { status: 503 }),
    ),
  )
  renderScreen()

  expect(await screen.findByText('Reminders are not set up on this server')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('does not offer a prompt the browser has already refused', async () => {
  installPush({ permission: 'denied' })
  serveKey()
  renderScreen()

  expect(await screen.findByText('Notifications are blocked for this app')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('turns reminders on for this device', async () => {
  const push = installPush()
  serveKey()
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      posted = await request.json()
      devices = 1
      return HttpResponse.json({ devices }, { status: 201 })
    }),
  )
  renderScreen()

  expect(
    await screen.findByText('No device has reminders turned on for your account yet.'),
  ).toBeInTheDocument()
  await userEvent.click(await screen.findByRole('button', TURN_ON))

  expect(await screen.findByText('Reminders are on for this device')).toBeInTheDocument()
  expect(
    await screen.findByText('Reminders go to 1 device on your account.'),
  ).toBeInTheDocument()
  expect(push.notification.requestPermission).toHaveBeenCalledOnce()
  expect(posted).toMatchObject({ endpoint: ENDPOINT })
})

test('a device with reminders on can turn them off', async () => {
  installPush({ permission: 'granted', subscribed: true })
  serveKey()
  devices = 1
  let forgotten: unknown = null
  server.use(
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      forgotten = await request.json()
      devices = 0
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Turn off on this device' }))

  expect(await screen.findByRole('button', TURN_ON)).toBeInTheDocument()
  expect(forgotten).toEqual({ endpoint: ENDPOINT })
})
```

`src/auth/useSession.test.tsx` exists since plan 7. Do not recreate it: its three tests stay exactly as they are (sign-out clears every cached query but the session, sign-in starts from an empty cache, and sign-out still shows the sign-in screen), and the push tests below reuse its module-level `queryClient`, `wrapper`, `signedInAsA` and `cachedKeys`. Make these changes:

1. Replace `import { beforeEach, expect, test } from 'vitest'` with `import { afterEach, beforeEach, expect, test } from 'vitest'`.
2. After `import { apiUrl } from '../mocks/apiUrl'`, add `import { ENDPOINT, installPush, uninstallPush } from '../mocks/pushApis'`.
3. After the `beforeEach(...)` block, add `afterEach(() => uninstallPush())`.
4. Append at the end of the file:

```tsx
/** Records the calls sign-out makes, in order, with the device's DELETE answering `status`. */
function serveSignOut(status = 204) {
  const calls: string[] = []
  server.use(
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      const { endpoint } = (await request.json()) as { endpoint: string }
      calls.push(`forget ${endpoint}`)
      return new HttpResponse(null, { status })
    }),
    http.post(apiUrl('/auth/logout'), () => {
      calls.push('logout')
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return calls
}

/** A signs out on a browser that has said something about push. */
async function signOutWithPush() {
  signedInAsA()
  queryClient.setQueryData(['push', 'device'], 'on')
  const { result } = renderHook(() => useSignOut(), { wrapper })

  await act(() => result.current.mutateAsync())
}

// The DELETE needs the session, and a shared phone must not go on reminding the
// person who just left it.
test('signing out forgets this device first, while the session still exists', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  const calls = serveSignOut()

  await signOutWithPush()

  expect(calls).toEqual([`forget ${ENDPOINT}`, 'logout'])
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(queryClient.getQueryData(['session'])).toBeNull()
  // What this browser said about push went with everything else of A's.
  expect(cachedKeys()).toEqual([['session']])
})

test('a device the server cannot forget does not keep anyone signed in', async () => {
  installPush({ permission: 'granted', subscribed: true })
  const calls = serveSignOut(500)

  await signOutWithPush()

  expect(calls).toEqual([`forget ${ENDPOINT}`, 'logout'])
  expect(queryClient.getQueryData(['session'])).toBeNull()
})

test('a browser without push simply signs out', async () => {
  const calls = serveSignOut()

  await signOutWithPush()

  expect(calls).toEqual(['logout'])
  expect(queryClient.getQueryData(['session'])).toBeNull()
})
```

- [ ] **Step 3: Run them to verify they fail**

From `frontend/`, run: `npx vitest run src/settings src/auth`
Expected: FAIL.
- `usePush.test.ts` cannot resolve `./usePush`, and `pushHandlers.test.ts` cannot load `public/push-handlers.js`.
- In `RemindersScreen.test.tsx`, most device tests fail because the old screen has no "This device" card and no buttons. The iPhone hint test passes already, because the old card always shows that text. The toggle test never sees the saved state, because the old screen only invalidates the query. The two profile-cache tests find the cache untouched, and the 404 test gets the load-error alert. The waiting-switches test finds breakfast still enabled, because the old screen never disables a switch.
- In `useSession.test.tsx`, the two new tests with a subscribed browser record only `logout`. Plan 7's three cache tests and 'a browser without push simply signs out' pass already.

- [ ] **Step 4: Implement**

Create `public/push-handlers.js`:

```js
/*
 * Meal reminders, inside the service worker.
 *
 * vite-plugin-pwa generates sw.js, and `workbox.importScripts` in vite.config.ts
 * loads this file into it. So this is plain JavaScript in the worker's global
 * scope: no imports, no bundling and no TypeScript. It is wrapped in a function
 * so that none of its names can collide with the generated worker's.
 *
 * The push payload is what the backend's WebPushChannel sends
 * (backend/app/reminders/channels.py):
 *   {"title": "Lunch", "body": "Nothing logged for lunch yet. Tap to log it.",
 *    "url": "/log?slot=lunch", "tag": "lunch-2026-08-17"}
 */
(() => {
  const FALLBACK = {
    title: 'Nutrient Tracker',
    body: 'Time to log your meal.',
    url: '/log',
    tag: undefined,
  }

  function readPayload(event) {
    if (!event.data) return FALLBACK
    try {
      const sent = event.data.json()
      const text = (value, otherwise) => (typeof value === 'string' ? value : otherwise)
      return {
        title: text(sent.title, FALLBACK.title),
        body: text(sent.body, FALLBACK.body),
        url: text(sent.url, FALLBACK.url),
        tag: text(sent.tag, FALLBACK.tag),
      }
    } catch {
      return FALLBACK
    }
  }

  /** The URL to open, on this app's own origin whatever the payload says. */
  function sameOrigin(raw) {
    const origin = self.location.origin
    try {
      const url = new URL(raw, origin)
      if (url.origin === origin) return url.href
    } catch {
      // Not a URL at all. The Log screen is the safe place to land.
    }
    return new URL(FALLBACK.url, origin).href
  }

  self.addEventListener('push', (event) => {
    // Always show what arrived, even a payload this file cannot read. A push that
    // shows nothing gets a generic notification on Chrome, and Safari can revoke
    // the subscription for it. Whether to send at all is the server's decision.
    const payload = readPayload(event)
    const options = { body: payload.body, icon: '/icon-192.png', data: { url: payload.url } }
    // One notification per slot and day: a second push with the same tag
    // replaces the first rather than stacking beside it.
    if (payload.tag !== undefined) options.tag = payload.tag
    event.waitUntil(self.registration.showNotification(payload.title, options))
  })

  async function openAt(url) {
    // Only windows this worker controls: navigate() refuses any other.
    const windows = await self.clients.matchAll({ type: 'window' })
    for (const client of windows) {
      try {
        await client.focus()
        await client.navigate(url)
        return
      } catch {
        // A window that cannot be focused or navigated. Try the next one.
      }
    }
    await self.clients.openWindow(url)
  }

  self.addEventListener('notificationclick', (event) => {
    event.notification.close()
    const url = sameOrigin(event.notification.data?.url ?? FALLBACK.url)
    event.waitUntil(openAt(url))
  })
})()
```

In `vite.config.ts`, inside `workbox: { ... }`, add these lines after the `navigateFallbackDenylist: [/^\/auth/, /^\/households/, /^\/foods/],` line:

```ts
        // The meal reminders' push and notification-click handlers: plain JS in
        // public/, loaded into the generated worker, which stays generateSW. The
        // file is precached too, so an edit to it changes sw.js and updates the
        // worker.
        importScripts: ['push-handlers.js'],
```

Create `src/settings/usePush.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { NewPushSubscription, PushDevices, PushPublicKey, PushUnsubscribe } from './types'

/**
 * Whether this browser can take meal reminders, and turning them on and off.
 *
 * - `unsupported`: no service worker, PushManager or Notification.
 * - `needs-install`: an iPhone or iPad outside the home screen. iOS delivers web
 *   push only to an installed app, and hides the APIs until then.
 * - `dev-worker`: the page is not under the production worker (`/sw.js`), which
 *   is the one with the push handler. In dev, MSW's worker owns the scope, or
 *   there is no worker at all.
 * - `ready`: a reminder can reach this browser.
 */
export type PushSupport = 'unsupported' | 'needs-install' | 'dev-worker' | 'ready'

/**
 * Where this browser stands, once it is `ready`.
 *
 * - `blocked`: notifications were denied, and asking again shows no prompt.
 * - `on`: permitted, and subscribed.
 * - `off`: neither, or permitted but no longer subscribed, as after signing out.
 */
export type DeviceState = 'blocked' | 'on' | 'off'

// The worker vite-plugin-pwa generates, which imports public/push-handlers.js.
const PRODUCTION_WORKER = '/sw.js'

function hasPushApis(): boolean {
  return (
    'serviceWorker' in navigator &&
    typeof window.PushManager !== 'undefined' &&
    typeof window.Notification !== 'undefined'
  )
}

function isAppleMobile(): boolean {
  const agent = navigator.userAgent
  // iPadOS asks for desktop sites, so an iPad says it is a Mac, but one with a
  // touch screen. Every browser on iOS is WebKit, so this is not only Safari.
  return (
    /iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && navigator.maxTouchPoints > 1)
  )
}

function isStandalone(): boolean {
  const displayMode =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(display-mode: standalone)').matches
  // Older iOS says it is on the home screen only through this non-standard flag.
  return displayMode || (navigator as Navigator & { standalone?: boolean }).standalone === true
}

export async function pushSupport(): Promise<PushSupport> {
  // Before the API check: Safari on an iPhone has none of them until it is
  // installed, and "unsupported" would hide the one thing that fixes it.
  if (isAppleMobile() && !isStandalone()) return 'needs-install'
  if (!hasPushApis()) return 'unsupported'
  try {
    // Not `.ready`, which never settles when no worker is registered at all, as
    // in dev with the mocks off. A worker still installing on a first visit
    // counts: subscribing waits for it.
    const registration = await navigator.serviceWorker.getRegistration()
    const worker = registration?.active ?? registration?.waiting ?? registration?.installing
    if (worker && new URL(worker.scriptURL).pathname.endsWith(PRODUCTION_WORKER)) return 'ready'
    return 'dev-worker'
  } catch {
    // A browser that refuses service workers here, such as a private window.
    return 'unsupported'
  }
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration()
  return (await registration?.pushManager.getSubscription()) ?? null
}

export async function thisDevice(): Promise<DeviceState> {
  if (Notification.permission === 'denied') return 'blocked'
  const subscription = await currentSubscription()
  return Notification.permission === 'granted' && subscription !== null ? 'on' : 'off'
}

/** The server's VAPID public key, as the bytes `pushManager.subscribe` takes. */
function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4)
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0))
}

/**
 * Ask for permission, subscribe this browser, and register it with the server.
 *
 * Call it straight from the tap. Resolves without subscribing when the prompt
 * is refused or dismissed, since that is the user's answer, not a failure.
 * Rejects with the `ApiError` when the server answers 503 (reminders are not set
 * up on it), or with whatever the browser or the server threw.
 */
export async function subscribeThisDevice(): Promise<void> {
  // First, before anything else is awaited. Safari shows the prompt only from
  // inside the tap that asked for it.
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return

  const { key } = await api.get<PushPublicKey>('/push/public-key')
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({
    // Every push shows a notification: Chrome requires the promise, and
    // push-handlers.js keeps it.
    userVisibleOnly: true,
    applicationServerKey: keyBytes(key),
  })

  const { keys } = subscription.toJSON()
  const body: NewPushSubscription = {
    endpoint: subscription.endpoint,
    keys: { p256dh: keys?.p256dh ?? '', auth: keys?.auth ?? '' },
    // Reminder times are wall-clock, and this is the only thing that tells the
    // server which wall.
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }
  try {
    await api.post<PushDevices>('/push/subscriptions', body)
  } catch (error) {
    // A browser subscription the server never stored would read as "on" here
    // and never be reminded. Undo it, so the button comes back.
    await subscription.unsubscribe().catch(() => false)
    throw error
  }
}

/**
 * Stop reminders on this browser: unsubscribe it, and tell the server.
 *
 * Never throws. Signing out calls it first, while the session still exists,
 * and a failure here must not keep anyone signed in.
 */
export async function unsubscribeThisDevice(): Promise<void> {
  let subscription: PushSubscription | null
  try {
    subscription = hasPushApis() ? await currentSubscription() : null
  } catch {
    return
  }
  if (subscription === null) return

  const body: PushUnsubscribe = { endpoint: subscription.endpoint }
  // Each half whatever happens to the other. The browser's own unsubscribe is
  // what stops the pushes: the push service then answers 410 to the server,
  // which forgets the device, so the DELETE is only the tidy way to get there.
  await subscription.unsubscribe().catch(() => false)
  await api.del('/push/subscriptions', body).catch(() => null)
}

export function usePushSupport() {
  return useQuery({ queryKey: ['push', 'support'], queryFn: pushSupport })
}

export function usePushKey() {
  return useQuery({
    queryKey: ['push', 'key'],
    queryFn: () => api.get<PushPublicKey>('/push/public-key'),
    // A 503 is an answer: this server sends no reminders. Retrying only delays it.
    retry: false,
  })
}

export function useThisDevice() {
  return useQuery({ queryKey: ['push', 'device'], queryFn: thisDevice })
}

function useDeviceChange(change: () => Promise<void>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: change,
    // Settled rather than succeeded: a refused prompt resolves, and a failed
    // subscribe may still have changed the permission.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['push', 'device'] })
      queryClient.invalidateQueries({ queryKey: ['settings', 'reminders'] })
    },
  })
}

export function useTurnOnThisDevice() {
  return useDeviceChange(subscribeThisDevice)
}

export function useTurnOffThisDevice() {
  return useDeviceChange(unsubscribeThisDevice)
}
```

Create `src/settings/useReminders.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { SavedProfile } from '../onboarding/useProfile'
import type { MealTimeSetting, ReminderChange, ReminderSettings } from './types'

/*
 * The key the profile wizard also invalidates: a profile save can switch a
 * snack on or off, which adds or removes its reminder here.
 */
const REMINDERS_KEY = ['settings', 'reminders'] as const

export function useReminders() {
  return useQuery({
    queryKey: REMINDERS_KEY,
    queryFn: () => api.get<ReminderSettings>('/settings/reminders'),
    retry: false,
  })
}

/**
 * The cached profile, with the reminder switches as the server now has them.
 *
 * The profile form sends every slot's `reminder_on` back with a save, from the
 * profile it last read. Left stale, that copy would switch a reminder turned off
 * here back on at the next profile save.
 */
function withReminders(profile: SavedProfile, slots: MealTimeSetting[]): SavedProfile {
  const switches = new Map<string, boolean>(slots.map((item) => [item.slot, item.reminder_on]))
  const rows = new Set(profile.meal_times.map((item) => item.slot))
  return {
    ...profile,
    meal_times: [
      ...profile.meal_times.map((item) => ({
        ...item,
        reminder_on: switches.get(item.slot) ?? item.reminder_on,
      })),
      // A profile saved before meal times existed has no row for a slot until a
      // switch here creates one, at the time the server reports.
      ...slots
        .filter((item) => !rows.has(item.slot))
        .map((item) => ({ ...item, is_enabled: true })),
    ],
  }
}

export function useSetReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (change: ReminderChange) =>
      api.patch<ReminderSettings>('/settings/reminders', change),
    onSuccess: (settings) => {
      // The answer is the whole screen's state, so there is nothing to refetch.
      queryClient.setQueryData(REMINDERS_KEY, settings)
      queryClient.setQueryData<SavedProfile | null>(['profile'], (profile) =>
        profile ? withReminders(profile, settings.slots) : profile,
      )
    },
  })
}
```

Replace `src/settings/RemindersScreen.tsx`:

```tsx
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { SLOT_LABELS } from '../log/types'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import {
  usePushKey,
  usePushSupport,
  useThisDevice,
  useTurnOffThisDevice,
  useTurnOnThisDevice,
} from './usePush'
import type { PushSupport } from './usePush'
import { useReminders, useSetReminder } from './useReminders'

const PROFILE_LINK =
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 ' +
  'text-sm font-medium text-surface'

const NOT_SET_UP = 'Reminders are not set up on this server'

/** Why this browser cannot take reminders, when it cannot. */
const UNAVAILABLE: Record<Exclude<PushSupport, 'ready'>, { title: string; detail: string }> = {
  unsupported: {
    title: 'This browser can’t show reminders',
    detail:
      'Reminders arrive as notifications, which this browser doesn’t support. Chrome, ' +
      'Edge, Firefox and Safari do, and so does this app installed on a phone.',
  },
  'needs-install': {
    title: 'Add this app to your home screen first',
    detail:
      'On an iPhone or iPad, iOS only delivers web notifications to installed apps. Tap ' +
      'Share, then Add to Home Screen, and open the app from there to turn reminders on.',
  },
  'dev-worker': {
    title: 'Reminders can’t be turned on from this page',
    detail:
      'This page isn’t running under the app’s own service worker, which is what receives ' +
      'reminders. If the app has only just loaded, reload the page. In development the ' +
      'mock worker takes its place, so reminders need a production build.',
  },
}

const NO_PROFILE =
  'Reminders go out at the meal times in your profile, so there is nothing to remind you ' +
  'about until you have told us about yourself.'

function isNotSetUp(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503
}

function Message({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <>
      <p className="mt-1 text-sm font-medium">{title}</p>
      {children !== undefined && <p className="mt-1 text-sm text-text-muted">{children}</p>}
    </>
  )
}

/** This browser, under the production worker: say where it stands, and offer the switch. */
function ReadyDevice() {
  const key = usePushKey()
  const device = useThisDevice()
  const turnOn = useTurnOnThisDevice()
  const turnOff = useTurnOffThisDevice()

  if (key.isPending || device.isPending) return <Skeleton className="mt-2 h-11 w-full" />
  if (isNotSetUp(key.error)) {
    return (
      <Message title={NOT_SET_UP}>
        The server has no push keys, so it has nothing to send reminders with. Your meal times
        and the switches below are still saved.
      </Message>
    )
  }
  if (key.isError || device.isError) {
    return (
      <p role="alert" className="mt-1 text-sm text-above-limit">
        Whether reminders can reach this device could not be checked. Please try again.
      </p>
    )
  }
  if (device.data === 'blocked') {
    return (
      <Message title="Notifications are blocked for this app">
        This browser has been told not to show its notifications. Allow them in the site
        settings, then come back here to turn reminders on.
      </Message>
    )
  }
  if (device.data === 'on') {
    return (
      <>
        <Message title="Reminders are on for this device" />
        <Button
          variant="quiet"
          className="mt-2 px-0"
          disabled={turnOff.isPending}
          onClick={() => turnOff.mutate()}
        >
          Turn off on this device
        </Button>
      </>
    )
  }
  return (
    <>
      <p className="mt-1 text-sm text-text-muted">
        The whole app rests on logging after each meal, so a nudge at the right time matters.
        You’ll be asked to allow notifications.
      </p>
      <Button
        variant="primary"
        className="mt-3"
        disabled={turnOn.isPending}
        // Straight from the tap: Safari only shows the permission prompt from inside one.
        onClick={() => turnOn.mutate()}
      >
        Turn on reminders on this device
      </Button>
      {turnOn.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {isNotSetUp(turnOn.error)
            ? NOT_SET_UP
            : 'Reminders could not be turned on for this device. Please try again.'}
        </p>
      )}
    </>
  )
}

function devicesLine(devices: number): string {
  if (devices === 0) return 'No device has reminders turned on for your account yet.'
  return `Reminders go to ${devices} ${devices === 1 ? 'device' : 'devices'} on your account.`
}

function ThisDevice({ devices }: { devices: number }) {
  const support = usePushSupport()
  const state = support.data

  return (
    <Card>
      <CardTitle>This device</CardTitle>
      {state === undefined ? (
        <Skeleton className="mt-2 h-11 w-full" />
      ) : state === 'ready' ? (
        <ReadyDevice />
      ) : (
        <Message title={UNAVAILABLE[state].title}>{UNAVAILABLE[state].detail}</Message>
      )}
      <p className="mt-3 text-xs text-text-muted">{devicesLine(devices)}</p>
    </Card>
  )
}

export function RemindersScreen() {
  const reminders = useReminders()
  const setReminder = useSetReminder()

  if (reminders.isPending) return <Skeleton className="h-64 w-full" />

  // A 404 means there is no profile yet, and so no meal times to remind about.
  if (reminders.error instanceof ApiError && reminders.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your meal times"
        description={NO_PROFILE}
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }
  if (reminders.isError || reminders.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your reminder settings could not be loaded. Please try again.
      </p>
    )
  }

  const data = reminders.data

  return (
    <section className="space-y-4">
      <ThisDevice devices={data.devices} />

      <Card>
        <CardTitle>Meal times and reminders</CardTitle>
        <p className="mt-1 mb-2 text-sm text-text-muted">
          These times also make your medication windows concrete — knowing breakfast is at 8:00
          is what lets the planner check the 60-minute levothyroxine gap.
        </p>

        <div className="divide-y divide-border">
          {data.slots.map((slot) => (
            <Toggle
              key={slot.slot}
              label={`${SLOT_LABELS[slot.slot]} · ${slot.time}`}
              description={
                slot.weekend_time === null ? undefined : `Weekends at ${slot.weekend_time}`
              }
              checked={slot.reminder_on}
              // The answer replaces every switch, so a second change waits for the first.
              disabled={setReminder.isPending}
              onChange={(on) => setReminder.mutate({ slot: slot.slot, reminder_on: on })}
            />
          ))}
        </div>

        {setReminder.isError && (
          <p role="alert" className="mt-2 text-sm text-above-limit">
            That reminder could not be changed. Please try again.
          </p>
        )}

        <p className="mt-2 text-xs text-text-muted">
          A reminder goes out at a slot’s time if nothing is logged or skipped for it yet, and
          never once you have. The mid-morning snack is off by default, since it’s optional.
        </p>
        <Link
          to="/profile/mealtimes"
          className="mt-1 inline-flex min-h-11 items-center text-sm text-accent underline"
        >
          Change your meal times
        </Link>
      </Card>
    </section>
  )
}
```

In `src/auth/useSession.ts`, add the import `import { unsubscribeThisDevice } from '../settings/usePush'` after the `../lib/api` import, and replace `useSignOut` with the following. Leave `notSession` and `useSignIn` as plan 7 left them. Only `mutationFn` changes: `onSuccess` keeps plan 7's order and its `removeQueries(notSession)`, which already takes every `['push', …]` query with the rest of the previous account's data, so push needs no removal of its own.

```ts
export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      // This device first, while there is still a session to forget it with: the
      // logout call takes no user. Otherwise whoever signs in next on this phone
      // would get this user's reminders. It never throws, so a failure there
      // cannot keep anyone signed in.
      await unsubscribeThisDevice()
      await api.post('/auth/logout', {})
    },
    onSuccess: () => {
      // The session first, so RequireAuth unmounts the screens; clearing the cache
      // before this leaves them subscribed to removed queries, and sign-out stalls.
      queryClient.setQueryData(['session'], null)
      // Everything else belongs to the user who just left, what this browser
      // said about push included.
      queryClient.removeQueries(notSession)
    },
  })
}
```

`src/shell/AppShell.tsx` needs no change. It still calls `signOut.mutate()`.

- [ ] **Step 5: Run the tests and the checks**

From `frontend/`, run: `npx vitest run && npx tsc -b && npm run lint && npm run build && grep -o 'importScripts("push-handlers.js")' dist/sw.js`
Expected: all PASS and clean.
- The new and replaced files pass in full: 24 tests in `usePush.test.ts`, 8 in `pushHandlers.test.ts`, 15 in `RemindersScreen.test.tsx` and 6 in `useSession.test.tsx` (plan 7's three and three new).
- The grep prints `importScripts("push-handlers.js")`, and `dist/push-handlers.js` exists. That is the generated worker loading the handlers.
- No other test used the deleted reminders handlers. Each test file stubs what it calls, and a request nobody stubbed fails the test that made it.

To check a real push by hand, serve the build on the origin the backend allows by default, with `npx vite preview --port 5173`. Point it at a backend with both VAPID keys set, sign in, and turn reminders on. Then, in Chrome DevTools, go to Application, Service workers, and use Push with `{"title":"Lunch","body":"Nothing logged for lunch yet. Tap to log it.","url":"/log?slot=lunch","tag":"lunch-2026-08-17"}`. A notification appears, and tapping it opens the Log screen at lunch.

- [ ] **Step 6: Commit**

```bash
git add public/push-handlers.js vite.config.ts src/settings src/auth/useSession.ts \
  src/auth/useSession.test.tsx src/mocks/pushApis.ts src/mocks/fixtures/more.ts \
  src/mocks/handlers/index.ts
git commit -m "feat(frontend): put reminders on the real endpoints, and push on this device

The Reminders screen now reads and switches the profile's own reminder_on
through /settings/reminders, and shows the server's answer as the saved state,
so a failed switch stays as it was. A switch also patches the cached profile.
The profile form sends every slot's reminder back with a save, and a stale copy
would switch this one back on.

Push belongs to one browser, so the screen asks the browser, not the server,
whether reminders can reach it, and push_granted leaves the contract for that
reason. The screen offers to turn reminders on only under the production
worker, /sw.js, because that is the worker carrying the push handler; in dev,
MSW's worker owns the scope. Safari on an iPhone is told to add the app to the
home screen first, because iOS delivers web push only to installed apps and
hides the APIs until then. A server without VAPID keys says so, rather than
subscribing a browser nothing will reach. A subscription the server could not
store is undone, so the button comes back.

The handlers are plain JS in public/push-handlers.js, loaded into the generated
worker with workbox.importScripts, so the worker stays generateSW. A push always
shows what arrived: Chrome penalises a silent push, and Safari can revoke the
subscription for one. A tap focuses an open window at the slot's Log screen or
opens a new one, and never leaves the app's origin.

Signing out unsubscribes this browser first, while the session still exists.
The logout call takes no user, and a shared phone would otherwise go on
reminding whoever left it. That step never throws, so it cannot keep anyone
signed in.

The reminders fixtures leave the dev handlers, which now hold only demo auth.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Frontend — household progress card, and Today explains a lowered target

This task makes two backend changes visible. First, the Household screen gets a "This week so far" card, read from Task 7's `GET /households/progress`. It has one line per member: days logged, and nutrient-days on track out of those measured, or a line saying the member is not sharing. The card has no nutrient or target it could show, because the backend never sends one. It exists only inside a household. A solo user never sees it and never asks for it, and a 404, or a 422 for a week that has not begun where the account keeps time, shows nothing rather than an error. Second, since Task 1, a harmful surplus lowers the next two days. A salty Sunday takes Monday's sodium ceiling from 2,000 mg to 1,400 mg. The nutrient bar annotates only a raised target, so today that drop happens with no reason given. The bar now says "Lowered by 600 mg after Sunday".

**Files:**
- Modify:
  - `src/households/useHousehold.ts`: the progress types and `useHouseholdProgress`; leaving drops the cached progress
  - `src/households/HouseholdScreen.tsx`: the progress card
  - `src/ui/NutrientBar.tsx`: a negative `carriedIn` is explained
- Test:
  - `src/households/HouseholdScreen.test.tsx`: `withHousehold()` now also stubs the progress endpoint, plus appended tests
  - `src/ui/NutrientBar.test.tsx`: append (the file exists)
  - `src/today/TodayScreen.test.tsx`: append

**Interfaces:**
- Consumes:
  - Task 7's contract: `GET /households/progress?start=YYYY-MM-DD` returns `{start_date, members: [{user_id, name, is_me, shared, tracked_days, nutrient_days_met, nutrient_days_measured}]}`.
    - It lists you first.
    - The counts are `null` when `shared` is false, or when the member has no profile.
    - It answers 404 when you are not in a household, and 422 when `start` is not a Sunday or the week has not begun.
  - Task 1's negative `carried_in` on `GET /targets/today`, with `carried_from` as the source day's full weekday name (`"Sunday"`), and `target_effective` lowered to match.
  - Existing helpers: `weekStartIso` (`src/plan/usePlan.ts`), `formatWithUnit` (`src/lib/format.ts`), `todayIso` (`src/today/useToday.ts`, in the tests only).
- Produces:
```ts
// src/households/useHousehold.ts
export interface MemberProgress {
  user_id: string; name: string; is_me: boolean; shared: boolean
  tracked_days: number | null; nutrient_days_met: number | null
  nutrient_days_measured: number | null
}
export interface HouseholdProgress { start_date: string; members: MemberProgress[] }
export function useHouseholdProgress(start: string)
  // query key ['household', 'progress', start]; resolves to null on a 404, or on a 422
  //   (the week has not begun where the account keeps time)

// src/ui/NutrientBar.tsx: carriedIn < 0 with carriedFrom renders
//   `Lowered by ${formatWithUnit(-carriedIn, unit)} after ${carriedFrom}`
```

- [ ] **Step 1: Write the failing tests**

In `src/households/HouseholdScreen.test.tsx`:

1. Replace the imports, the lines above `const SUDEV = {`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { HouseholdScreen } from './HouseholdScreen'
```

with:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { HouseholdScreen } from './HouseholdScreen'
import type { HouseholdProgress, MemberProgress } from './useHousehold'
```

2. Directly after the `HOUSEHOLD` constant (after its closing `}`), add:

```tsx
/*
 * Task 7's contract: you first, then the others. Counts of days only -- the
 * backend never sends a nutrient or a target, because a target is health data.
 */
const MY_WEEK: MemberProgress = {
  user_id: 'u-sudev',
  name: 'Sudev',
  is_me: true,
  shared: true,
  tracked_days: 3,
  nutrient_days_met: 41,
  nutrient_days_measured: 60,
}

const AMMAS_WEEK: MemberProgress = {
  user_id: 'u-amma',
  name: 'Amma',
  is_me: false,
  shared: true,
  tracked_days: 2,
  nutrient_days_met: 30,
  nutrient_days_measured: 38,
}

const NO_FIGURES = { tracked_days: null, nutrient_days_met: null, nutrient_days_measured: null }

const PROGRESS: HouseholdProgress = { start_date: '2026-09-20', members: [MY_WEEK, AMMAS_WEEK] }

function progressWith(amma: Partial<MemberProgress>): HouseholdProgress {
  return { ...PROGRESS, members: [MY_WEEK, { ...AMMAS_WEEK, ...amma }] }
}

/** The `start` of every progress request, in order. */
let progressStarts: string[] = []
```

3. Replace the `beforeEach` block:

```tsx
beforeEach(() => {
  server.use(http.get(apiUrl('/auth/me'), () => HttpResponse.json(SUDEV)))
})
```

with:

```tsx
beforeEach(() => {
  progressStarts = []
  server.use(http.get(apiUrl('/auth/me'), () => HttpResponse.json(SUDEV)))
})
```

4. Replace `withHousehold`:

```tsx
function withHousehold() {
  server.use(http.get(apiUrl('/households/me'), () => HttpResponse.json(HOUSEHOLD)))
}
```

with the following. A screen with a household now also asks for the week's progress, and a request nobody stubbed fails the test.

```tsx
function stubProgress(body: HouseholdProgress = PROGRESS) {
  server.use(
    http.get(apiUrl('/households/progress'), ({ request }) => {
      progressStarts.push(new URL(request.url).searchParams.get('start') ?? '')
      return HttpResponse.json(body)
    }),
  )
}

function withHousehold(household = HOUSEHOLD) {
  server.use(http.get(apiUrl('/households/me'), () => HttpResponse.json(household)))
  stubProgress()
}
```

5. Append to the end of the file:

```tsx
// --- this week's progress ------------------------------------------------------
//
// Weekly progress is shared by default, so whoever cooks can see how the week is
// going. What reaches the household is counts of days, never a target: a
// 1,500 mg sodium cap says hypertension as plainly as the diagnosis would.

test('shows each member’s week as counts of days, you first', async () => {
  withHousehold()
  renderScreen()

  const list = await screen.findByRole('list', { name: 'Household progress' })
  const rows = within(list).getAllByRole('listitem')
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(rows[1]).toHaveTextContent('Amma: on track 30 of 38 nutrient-days, 2 days logged')
})

test('asks for the week in progress, from its Sunday', async () => {
  withHousehold()
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(progressStarts).toHaveLength(1)
  const [start] = progressStarts
  // Both are plain calendar dates, parsed as UTC midnight: whole days apart.
  const daysIn = (Date.parse(todayIso()) - Date.parse(start)) / 86_400_000
  expect(new Date(Date.parse(start)).getUTCDay()).toBe(0)
  expect(daysIn).toBeGreaterThanOrEqual(0)
  expect(daysIn).toBeLessThan(7)
})

test.each([
  {
    state: 'not sharing progress',
    week: { shared: false, ...NO_FIGURES },
    text: 'Amma: not sharing progress',
  },
  {
    state: 'without a profile',
    week: NO_FIGURES,
    text: 'Amma: has not set up a profile yet',
  },
  {
    // Early in the week, or on its Sunday: today counts only once it is over.
    state: 'with no finished day logged',
    week: { tracked_days: 0, nutrient_days_met: 0, nutrient_days_measured: 0 },
    text: 'Amma: no days logged yet',
  },
  {
    state: 'one day in',
    week: { tracked_days: 1, nutrient_days_met: 12, nutrient_days_measured: 14 },
    text: 'Amma: on track 12 of 14 nutrient-days, 1 day logged',
  },
])('a member $state reads as “$text”', async ({ week, text }) => {
  withHousehold()
  stubProgress(progressWith(week))
  renderScreen()

  expect(await screen.findByText(text)).toBeInTheDocument()
})

// Your own row always shows you your figures. With sharing off it has to say
// that nobody else sees them, or it reads as if the household does.
test('says when your own figures are visible only to you', async () => {
  withHousehold() // Sudev shares no progress
  renderScreen()

  expect(await screen.findByText(/only you can see this/i)).toBeInTheDocument()
})

test('says nothing of the kind when you share your progress', async () => {
  withHousehold({
    ...HOUSEHOLD,
    members: HOUSEHOLD.members.map((member) => ({ ...member, share_progress: true })),
  })
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(screen.queryByText(/only you can see this/i)).not.toBeInTheDocument()
})

test('changing what you share refreshes this week’s progress', async () => {
  withHousehold()
  server.use(
    http.patch(apiUrl('/households/visibility'), () =>
      HttpResponse.json({ share_progress: true, share_health: false }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  await userEvent.click(screen.getByRole('checkbox', { name: /share my daily progress/i }))

  await waitFor(() => expect(progressStarts).toHaveLength(2))
})

test('says so when this week’s progress cannot be loaded', async () => {
  withHousehold()
  server.use(
    http.get(apiUrl('/households/progress'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  expect(await screen.findByRole('alert')).toHaveTextContent(/progress could not be loaded/i)
})

// The household can go between the two requests -- left from another device,
// say. That is not an error; the household query catches up on its own.
test('shows no progress card when the household has gone', async () => {
  withHousehold()
  server.use(
    http.get(
      apiUrl('/households/progress'),
      () => new HttpResponse('You are not in a household yet', { status: 404 }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev Home')
  await waitFor(() => expect(screen.queryByText('This week so far')).not.toBeInTheDocument())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// The browser's calendar can reach a Sunday before the account's timezone does.
// That week has not begun where the account keeps time: not an error, and
// nothing to show yet.
test('shows no progress card for a week not yet begun where the account keeps time', async () => {
  withHousehold()
  server.use(
    http.get(
      apiUrl('/households/progress'),
      () => new HttpResponse('That week has not started yet', { status: 422 }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev Home')
  await waitFor(() => expect(screen.queryByText('This week so far')).not.toBeInTheDocument())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// Solo is the default and the full app. A card about other people's weeks has
// nothing to say to someone on their own, and must not ask for one.
test('a user on their own sees no progress card, and nothing asks for one', async () => {
  withoutHousehold()
  stubProgress()
  renderScreen()

  await screen.findByText(/tracking on your own/i)
  expect(screen.queryByText('This week so far')).not.toBeInTheDocument()
  expect(progressStarts).toEqual([])
})

// The old household's weeks are not yours to see once you have left, and the
// next household must not open on them while its own counts load.
test('leaving forgets the old household’s weeks', async () => {
  let calls = 0
  withHousehold()
  server.use(
    http.get(apiUrl('/households/progress'), async () => {
      calls += 1
      // The new household's counts never arrive, so any row shown after the
      // move can only have come from the old household.
      if (calls > 1) await delay('infinite')
      return HttpResponse.json(PROGRESS)
    }),
    http.post(apiUrl('/households/leave'), () => new HttpResponse(null, { status: 204 })),
    http.post(apiUrl('/households'), () =>
      HttpResponse.json(
        { id: 'h2', name: 'New Home', members: [HOUSEHOLD.members[1]] },
        { status: 201 },
      ),
    ),
  )
  renderScreen()

  await screen.findByText('Amma: on track 30 of 38 nutrient-days, 2 days logged')
  await userEvent.click(screen.getByRole('button', { name: /leave household/i }))
  await userEvent.type(await screen.findByLabelText('Household name'), 'New Home')
  await userEvent.click(screen.getByRole('button', { name: /create household/i }))

  expect(await screen.findByText('New Home')).toBeInTheDocument()
  expect(screen.getByText('This week so far')).toBeInTheDocument()
  expect(screen.queryByText(/^Amma:/)).not.toBeInTheDocument()
})
```

Append to `src/ui/NutrientBar.test.tsx`:

```tsx
// --- a lowered target -----------------------------------------------------------
//
// A harmful surplus lowers the next two days: a 4,000 mg sodium Sunday takes
// 600 mg off each of Monday's and Tuesday's 2,000 mg ceilings. A ceiling that
// drops overnight with no reason given reads as a bug.

// Sodium has no ICMR upper limit of its own, so the API sends `tul: null`.
const SODIUM = { name: 'Sodium', unit: 'mg', ear: null, tul: null, kind: 'ceiling' } as const

test('says what lowered a ceiling, and after which day', () => {
  render(
    <NutrientBar {...SODIUM} consumed={900} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.getByText('Lowered by 600 mg after Sunday')).toBeInTheDocument()
})

// A negative carry is not a carry to make up, and a sign in front of a number
// is easy to miss.
test('does not present a lowered ceiling as something carried', () => {
  render(
    <NutrientBar {...SODIUM} consumed={900} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.queryByText(/carried from/i)).not.toBeInTheDocument()
})

// The day is judged against the lowered ceiling, which is its limit: 1,500 mg is
// under Sunday's 2,000 mg but past today's 1,400 mg.
test('judges the day against the lowered ceiling', () => {
  render(
    <NutrientBar {...SODIUM} consumed={1500} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.getByText('past the upper limit')).toBeInTheDocument()
})
```

Append to `src/today/TodayScreen.test.tsx`:

```tsx
/*
 * The day after a 4,000 mg sodium Sunday, the ceiling is 600 mg lower. Today
 * says why, beside the calcium carry that raised a target, which it still shows.
 * The real API sends `tul: null` for sodium (ICMR set no upper limit), so the
 * lowered ceiling is what the day is judged by. The fixture's `tul: 2000` would
 * hide that.
 */
test('says why a ceiling was lowered, beside a target that was raised', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () =>
      HttpResponse.json({
        ...TODAY_FIXTURE,
        nutrients: TODAY_FIXTURE.nutrients.map((nutrient) =>
          nutrient.code === 'sodium'
            ? {
                ...nutrient,
                tul: null,
                target_effective: 1400,
                carried_in: -600,
                carried_from: 'Sunday',
                consumed: 900,
              }
            : nutrient,
        ),
      }),
    ),
  )
  renderScreen()

  expect(await screen.findByText('Lowered by 600 mg after Sunday')).toBeInTheDocument()
  expect(screen.getByText('900 / 1,400 mg')).toBeInTheDocument()
  expect(screen.getByText('+180 mg carried from Friday')).toBeInTheDocument()
})
```

Where the figures come from:
- `formatWithUnit(600, 'mg')` is `600 mg`. Milligrams at or above 10 round to a whole number.
- The amounts line is `formatAmount(900, 'mg')` then `formatWithUnit(1400, 'mg')`. With en-IN grouping, that reads `900 / 1,400 mg`.
- 2026-09-20 is a Sunday. It appears only in the fixture's `start_date`, which the screen does not read.

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run src/households src/ui/NutrientBar.test.tsx src/today/TodayScreen.test.tsx`
Expected: FAIL, 13 failed:
- **Household: 11 fail.** There is no progress card yet, so each fails on its first `findBy`. For example: `Unable to find role="list" and name "Household progress"`, or `Unable to find an element with the text: Amma: not sharing progress`.
- **Household: 3 pass already.** These are `shows no progress card when the household has gone`, `shows no progress card for a week not yet begun where the account keeps time` and `a user on their own sees no progress card, and nothing asks for one`, since no card exists to show. All three guard the card once it exists.
- **NutrientBar: 1 fails, 2 pass.** `says what lowered a ceiling, and after which day` fails with `Unable to find an element with the text: Lowered by 600 mg after Sunday`. The other two lock in behaviour that already holds.
- **Today: 1 fails,** on the same missing text.
- **Unchanged tests still pass.** `withHousehold()` now stubs a request nobody makes yet.

`npx tsc -b` would reject the test's type import of `HouseholdProgress` and `MemberProgress`. Vitest strips type-only imports, so the run above is unaffected.

- [ ] **Step 3: The progress query**

In `src/households/useHousehold.ts`, add the following after the `Household` interface:

```ts
/**
 * One member's week, as the household may see it: counts of days, never a
 * nutrient or a target. CONTRACT for `GET /households/progress?start=`,
 * implemented by the backend's `app/households/router.py`.
 */
export interface MemberProgress {
  user_id: string
  name: string
  is_me: boolean
  /** Whether you may see this member's counts. Always true on your own row. */
  shared: boolean
  /** Logged days that have ended. Null when not shared, or with no profile yet. */
  tracked_days: number | null
  /** Nutrient-days on track: one nutrient on one logged day, met as the report meets it. */
  nutrient_days_met: number | null
  nutrient_days_measured: number | null
}

export interface HouseholdProgress {
  /** The Sunday the week starts on. */
  start_date: string
  /** You first, then everyone else in the order they joined. */
  members: MemberProgress[]
}
```

Add this after `useHousehold`:

```ts
/**
 * One week's progress for the whole household. Null when you are not in one (a
 * 404), or when the week has not begun where your account keeps time (a 422:
 * this browser's calendar can reach a Sunday first). Neither is an error.
 */
export function useHouseholdProgress(start: string) {
  return useQuery({
    // Under 'household', so every invalidation of the household -- a change of
    // what you share, above all -- refreshes the counts with it.
    queryKey: ['household', 'progress', start],
    queryFn: async () => {
      try {
        return await api.get<HouseholdProgress>(`/households/progress?start=${start}`)
      } catch (error) {
        // 404: you are no longer in a household. 422: this browser's Sunday came
        // before the account's, so the week has not begun where the account keeps
        // time. Both are calm states, and the card shows nothing.
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
          return null
        }
        throw error
      }
    },
    retry: false,
  })
}
```

In `useLeaveHousehold`, replace `onSuccess: () => queryClient.setQueryData(['household'], null),` with:

```ts
    onSuccess: () => {
      queryClient.setQueryData(['household'], null)
      // The old household's weeks are not yours to see any more, and a household
      // started or joined next must not open on them while its own counts load.
      queryClient.removeQueries({ queryKey: ['household', 'progress'] })
    },
```

- [ ] **Step 4: The progress card**

In `src/households/HouseholdScreen.tsx`:

1. Add `import { weekStartIso } from '../plan/usePlan'` after the `../auth/useSession` import.

2. Replace the `./useHousehold` import:

```tsx
import {
  useAcceptInvite,
  useCreateHousehold,
  useHousehold,
  useInvite,
  useLeaveHousehold,
  useUpdateVisibility,
} from './useHousehold'
```

with:

```tsx
import {
  useAcceptInvite,
  useCreateHousehold,
  useHousehold,
  useHouseholdProgress,
  useInvite,
  useLeaveHousehold,
  useUpdateVisibility,
} from './useHousehold'
import type { MemberProgress } from './useHousehold'
```

3. Add the following between `NoHousehold` and `export function HouseholdScreen()`:

```tsx
/**
 * One member's week as one sentence. Counts of days only: the backend sends no
 * nutrient and no target, because a target is health data -- a 1,500 mg sodium
 * cap says hypertension as plainly as the diagnosis would.
 */
function progressLine(member: MemberProgress): string {
  if (!member.shared) return `${member.name}: not sharing progress`
  const tracked = member.tracked_days
  const met = member.nutrient_days_met
  const measured = member.nutrient_days_measured
  if (tracked === null || met === null || measured === null) {
    return `${member.name}: has not set up a profile yet`
  }
  if (tracked === 0) return `${member.name}: no days logged yet`
  const days = tracked === 1 ? '1 day' : `${tracked} days`
  return `${member.name}: on track ${met} of ${measured} nutrient-days, ${days} logged`
}

/** The week in progress, for everyone in the household who shares it. */
function ProgressCard({ sharingMine }: { sharingMine: boolean }) {
  const progress = useHouseholdProgress(weekStartIso())

  // Null is a 404 or a 422. A 404: the household went between the two requests,
  // left from another device, say, and the household query catches up on its own.
  // A 422: the week has not begun where the account keeps time, because this
  // browser's calendar reached Sunday first. Either way there is nothing to show yet.
  if (progress.data === null) return null

  return (
    <Card className="mt-6">
      <CardTitle>This week so far</CardTitle>
      <p className="mt-1 text-xs text-text-muted">
        Days logged, and nutrient-days on track out of those measured: a nutrient-day is
        one nutrient on one logged day. A day counts once it is over. Nobody’s targets or
        health details appear here.
      </p>
      {progress.isPending && <Skeleton className="mt-3 h-16 w-full" />}
      {progress.isError && (
        <p role="alert" className="mt-3 text-sm text-above-limit">
          This week’s progress could not be loaded.
        </p>
      )}
      {progress.data && (
        <ul aria-label="Household progress" className="mt-2 divide-y divide-border">
          {progress.data.members.map((member) => (
            <li key={member.user_id} className="py-2 text-sm">
              {progressLine(member)}
              {/*
                Your own row always shows you your figures, so with sharing off it
                has to say nobody else sees them, or it reads as if they do.
              */}
              {member.is_me && !sharingMine && (
                <span className="block text-xs text-text-muted">
                  Only you can see this: you are not sharing your progress.
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
```

4. In `HouseholdScreen`, add the following between the members list's closing `</ul>` and `<div className="mt-6 grid gap-6 md:grid-cols-2">`:

```tsx
      <ProgressCard sharingMine={me?.share_progress ?? true} />
```

The card is its own component, rendered only in the household branch. That is what keeps a solo user from making the request at all: its hook runs only when the card mounts. `sharingMine` falls back to `true` exactly as the sharing checkbox does, so the two never disagree.

- [ ] **Step 5: Explain a lowered target on Today**

In `src/ui/NutrientBar.tsx`:

1. In `NutrientBarProps`, replace:

```tsx
  /** What the ledger added to today's target. */
  carriedIn?: number
```

with:

```tsx
  /**
   * What the ledger added to today's target. Negative when a harmful surplus
   * lowered it: a 4,000 mg sodium Sunday takes 600 mg off Monday's ceiling.
   */
  carriedIn?: number
```

2. Directly after the positive-carry annotation (the `{carriedIn !== undefined && carriedIn > 0 && carriedFrom !== undefined && (…)}` block that ends in `carried from ${carriedFrom}`), add:

```tsx
        {/*
          A lowered target needs its reason as much as a raised one: a sodium
          ceiling that drops to 1,400 mg with no word of why reads as a bug.
        */}
        {carriedIn !== undefined && carriedIn < 0 && carriedFrom !== undefined && (
          <span className="text-carried">
            {`Lowered by ${formatWithUnit(-carriedIn, unit)} after ${carriedFrom}`}
          </span>
        )}
```

`formatWithUnit` is already imported. The carried segment in the track stays positive-only, so a lowered ceiling draws no segment. The track still spans the lowered ceiling, and an overshoot of it gets its target tick as before. `TodayScreen.tsx` needs no change: `nutrientBarProps` already passes `carried_in` and `carried_from` through, whatever their sign. The energy `StatTile` is left alone.

- [ ] **Step 6: Run the tests and the checks**

Run: `npx vitest run && npx tsc -b && npm run lint`
Expected: all PASS, and `tsc` and `oxlint` are clean.

- [ ] **Step 7: Commit**

```bash
git add src/households/useHousehold.ts src/households/HouseholdScreen.tsx \
  src/households/HouseholdScreen.test.tsx src/ui/NutrientBar.tsx src/ui/NutrientBar.test.tsx \
  src/today/TodayScreen.test.tsx
git commit -m "feat(frontend): show the household's week as counts, and say why a target dropped

The Household screen gains a This week so far card, read from GET
/households/progress. Each member gets one line: days logged, and
nutrient-days on track out of those measured. A member who does not share
progress gets a line saying so. The card cannot show a nutrient or a target,
because the backend sends none: a target is health data.

- A solo user sees no card and makes no request.
- A 404, meaning the household went from another device, and a 422 for a
  week not yet begun where the account keeps time, show nothing rather
  than an error.
- Your own row says when only you can see it.
- Leaving drops the old household's weeks from the cache, so the next
  household never opens on them.
- The query sits under 'household', so changing what you share refreshes it.

A harmful surplus now lowers the next two days, so a sodium ceiling can drop
to 1,400 mg overnight. The nutrient bar annotated only a raised target, so
the drop came with no reason. It now reads 'Lowered by 600 mg after Sunday'.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: End-to-end walks, READMEs, and the plan record

**Files:**
- Modify:
  - `frontend/e2e/smoke.spec.ts`: two walks appended; the header comment gains two bullets
  - `frontend/src/ui/feedback.tsx`: delete `DemoDataBanner`, which has no users after Tasks 8 and 12
  - `frontend/src/mocks/browser.ts`: refresh its stale comment
  - `frontend/src/main.tsx`: the stale "self-contained demo" comment above `startMocks`
  - `frontend/src/mocks/fixtures/today.ts`: drop the stale "DemoDataBanner" mention
  - `backend/app/nutrition_core/recalibration.py`: five comment lines added above `DRIFT_TOLERANCE_KG_PER_WEEK`, which record the oldest-point gap
  - `frontend/README.md`
  - `docs/superpowers/plans/README.md`
  - `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`: contract rows
  - `docs/superpowers/plans/2026-09-24-weight-and-cycle.md`: correct one overclaim
  - this file: its Status line

**Interfaces:**
- Consumes the screens exactly as Tasks 8 and 12 built them:
  - the Report screen's `h2` week range, "Previous week" and "Next week" buttons, and its empty state "Nothing was logged this week";
  - the Reminders screen's per-slot switches, named like `Dinner · 20:30`.

- [ ] **Step 1: Append the two walks**

Both walks go at the end of `test.describe('the tracking loop', ...)` in `frontend/e2e/smoke.spec.ts`, after the cycle walk. `globalSetup` resets the e2e user once per run, and a separate file would sort before `smoke.spec.ts` and land before onboarding. The cycle walk switched the profile to female, which neither walk depends on.

```ts
  test('the report opens on the last complete week and steps between weeks', async ({ page }) => {
    await page.goto('/report')

    // The e2e user was reset at the start of the run, so last week has nothing in it:
    // the report says so rather than drawing a week of zeros.
    const range = page.getByRole('heading', { level: 2 })
    await expect(range).toBeVisible()
    const lastWeek = (await range.textContent()) ?? ''
    await expect(page.getByText('Nothing was logged this week')).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Back one week, and forward again to where it started.
    await page.getByRole('button', { name: 'Previous week' }).click()
    await expect(range).not.toHaveText(lastWeek)
    await page.getByRole('button', { name: 'Next week' }).click()
    await expect(range).toHaveText(lastWeek)

    // Forward once more is the week in progress, and no further.
    await page.getByRole('button', { name: 'Next week' }).click()
    await expect(page.getByText('In progress')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Next week' })).toBeDisabled()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('a meal reminder can be switched off, and stays off', async ({ page }) => {
    await page.goto('/reminders')
    await expect(page.getByRole('note')).toHaveCount(0)

    // The dev server registers no service worker, so this page cannot subscribe the
    // browser -- but the per-slot settings are the real API either way.
    const dinner = page.getByRole('switch', { name: /dinner · 20:30/i })
    await expect(dinner).toBeChecked()

    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' && response.url().includes('/settings/reminders'),
    )
    await dinner.click()
    expect((await saved).ok()).toBe(true)
    await expect(dinner).not.toBeChecked()

    // A reload reads it back from the server, not from this page's cache.
    await page.reload()
    await expect(page.getByRole('switch', { name: /dinner · 20:30/i })).not.toBeChecked()

    // The mid-morning snack reminds nobody by default.
    await expect(page.getByRole('switch', { name: /mid-morning snack|snack 1/i })).not.toBeChecked()
  })
```

Check the snack switch's accessible name against Task 12's `RemindersScreen` (it is `${SLOT_LABELS[slot]} · ${time}`), and adjust the regular expression to the label `SLOT_LABELS.snack1` actually holds.

Add two bullets to the header comment's list:
- "The weekly report on the real week walk: last week opens first, an empty week says so, and the week in progress is as far as it goes."
- "Meal reminders on the real settings endpoint: a slot switched off stays off across a reload, and the mid-morning snack starts off."

- [ ] **Step 2: Tidy what Tasks 8 and 12 left behind**

1. In `frontend/src/ui/feedback.tsx`, delete `DemoDataBanner` and its doc comment. Every screen that carried it is on a real endpoint now. Then run `grep -rn DemoDataBanner frontend/src`, which should print nothing.
2. In `frontend/src/mocks/browser.ts`, replace the comment that says the worker "only answers the endpoints plans 3-8 have yet to build" with:
   `// In dev the worker answers only the opt-in demo-auth handlers; every other request passes through to the real API.`
3. In `frontend/src/mocks/fixtures/today.ts`, drop the sentence that says the Today screen carries a `DemoDataBanner`.
4. In `frontend/src/main.tsx`, the doc comment above `startMocks` still offers `VITE_USE_MOCKS=true` as "a self-contained demo", which no fixture handler is left to serve. Replace the whole comment with:
   ```ts
   /**
    * Mocks are on in dev by default and off in a production build. Set
    * `VITE_USE_MOCKS=false` to run dev with no worker at all. With no fixture
    * handlers left, the worker serves only opt-in demo auth (`VITE_DEMO_AUTH=true`).
    * The import is dynamic so MSW is tree-shaken out of the production bundle
    * entirely rather than shipped and skipped.
    */
   ```
5. In `backend/app/nutrition_core/recalibration.py`, record the gap that plan 7's confirmation rule leaves. Plan 7's fix wave already limited the comment above `DRIFT_TOLERANCE_KG_PER_WEEK` to the newest weigh-in, so there is no sentence to replace. Directly after the line
   `# Weighing weekly, a step therefore needs four weigh-ins across three weeks.`
   and before `DRIFT_TOLERANCE_KG_PER_WEEK = 0.25`, insert:
   ```python
   # A single blip cannot step on its own as the newest weigh-in: the next one dilutes
   # it. It can still move a step as the OLDEST point of a fresh window -- the onboarding
   # weigh-in, a step's own date, or the first weigh-in after a goal change -- once it is
   # off by more than ~0.83 kg (0.25 / 0.3, the four-point slope's weight on its first
   # point). Recorded as a known gap.
   ```
   In `docs/superpowers/plans/2026-09-24-weight-and-cycle.md`, in the "How the trend is read" decision, replace the sentence "A single blip is always either the newest point of the first reading or a diluted point of the next, so it can never step." with "As the newest weigh-in, a single blip is either the newest point of the first reading or a diluted point of the next, so it cannot step on its own; as the oldest point of a fresh window it still can (see Known gaps)." Add the same gap to that file's "Known gaps to record in the closeout" list.

- [ ] **Step 3: Run the walks against the real stack**

From the repo root, with Postgres up (`docker compose up -d db`):

```bash
cd backend && uv run python -m scripts.e2e_seed
cd backend && (uv run uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &) && sleep 3 && curl -sf http://localhost:8000/health
cd frontend && npm run test:e2e
```

Expected: `9 passed` (or `8 passed, 1 skipped` where the database has no slot-tagged dishes). Stop the API afterwards: `pkill -f "uvicorn app.main:app --port 8000"`. The scheduler stays off: `SCHEDULER_ENABLED` is unset.

- [ ] **Step 4: Update the READMEs and the contract table**

In `frontend/README.md`:
- Under "Which screens are real", replace the two paragraphs with:

  > **Live against the real backend:** every screen. That covers sign-in, household (with the week's shared progress), food search, the onboarding questionnaire and profile, Today, meal logging, the meal plan, weight, cycle tracking, the weekly report and reminders.
  >
  > **Push reminders need a production build.** The browser subscribes only under the production service worker (`npm run build && npm run preview`), and the backend sends only with VAPID keys set and `SCHEDULER_ENABLED=true`. See `backend/.env.example`.

- Replace "Every screen but Report and Reminders talks to the real FastAPI backend" with "Every screen talks to the real FastAPI backend".
- Replace the whole "### Without a backend" subsection (the heading through "it hands a session to anyone who asks.") with:

  ````markdown
  ### Without a Google OAuth client

  Every screen needs the backend and Postgres (see above). Demo auth gets you past the sign-in
  screen without Google:

  ```bash
  VITE_DEMO_AUTH=true npm run dev
  ```

  This fakes `/auth/*` in the browser only. The backend still has no session, so every other
  request answers 401: you get the shell and each screen's error state, not your data. The
  end-to-end walk gets a real session a different way, through `backend/scripts/e2e_session.py`
  (see "End to end"). **Never enable demo auth in a deployed build.** It hands a session to
  anyone who asks.
  ````

- In the paragraph that begins "Mocks are on in dev and off in a production build", replace "Override with `VITE_USE_MOCKS=false` (dev against a fully real backend) or `true` (a self-contained demo build)." with "No fixture handlers are left, so the mock worker serves only opt-in demo auth. Override with `VITE_USE_MOCKS=false` (no worker at all) or `true`."
- Under "End to end", change the comment to `# Playwright: onboarding -> log -> dashboard, then the plan, weight, cycle, report and reminders`.

In `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`, replace the report and reminders rows of the contract table with:

```
| `GET /reports/week?start=` | `src/report/types.ts` | Plan 8 (built; contract amended) |
| `GET/PATCH /settings/reminders`, `GET /push/public-key`, `POST/DELETE /push/subscriptions` | `src/settings/types.ts` | Plan 8 (built; contract amended) |
```

In `docs/superpowers/plans/README.md`:
- Change row 8 to:

  `| 8 | Weekly report & reminders | Nutrient report, uncompensated gaps, next-week suggestions, web push at meal times | **Complete** — `2026-09-24-report-and-reminders.md`. The report is derived on demand; suggestions weight the next week's plan; reminders are web push behind a channel interface, sent by an opt-in in-process scheduler or a cron CLI |`

- After the paragraph about plan 7, add: "Plan 8's decisions and the gaps it leaves are recorded at the top and bottom of `2026-09-24-report-and-reminders.md`."

In this file, add a `**Status:**` line under the Spec paragraph at the top, in the form the other plans use: the counts from the final run, and the checks that passed.

- [ ] **Step 5: Run everything**

```bash
cd backend  && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npx vitest run && npx tsc -b && npm run lint && npm run build
```

Expected: every command clean. Record the counts in the Status line.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e frontend/src/ui/feedback.tsx frontend/src/mocks/browser.ts \
  frontend/src/main.tsx frontend/src/mocks/fixtures/today.ts frontend/README.md \
  backend/app/nutrition_core/recalibration.py \
  docs/superpowers/plans/README.md docs/superpowers/plans/2026-09-24-report-and-reminders.md \
  docs/superpowers/plans/2026-09-24-weight-and-cycle.md \
  docs/superpowers/specs/2026-08-17-ui-foundation-design.md
git commit -m "docs: record plan 8, the weekly report and reminders, and add its end-to-end walks

The report and reminders screens were the last on fixtures; both now walk
the real API end to end. DemoDataBanner has no users left and goes.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Known gaps to record in the closeout

**Recalibration**
- **A blip can still step as the oldest point of a fresh window** (carried from plan 7). That covers the onboarding weigh-in, a step's own date, and the first weigh-in after a goal change. A reading more than about 0.83 kg off can move a bounded step on the fourth weigh-in. A typed onboarding weight is the realistic case. Leaving the anchor weigh-in out of its own window's slope would close it.

**The ledger and the report**
- **Carries onto untracked days are not reported.** A shortfall carried onto a day with nothing logged is neither made up nor counted as uncompensated, because the walk never costs an untracked day.
- **A week's figures can differ slightly from what Today showed.** The report walks from a clean slate four days before Sunday, as Today does. Chains of unmet carries older than that are not followed.
- **An old week is re-costed against today's profile and food tables.** The report is derived, never stored.
- **EAR and TUL come from the week's first day.** The report loads its context at the Sunday, so the EAR of an energy-scaled B vitamin, and an overlay-touched energy-derived target, do not follow a mid-week recalibration.
- **A day logged only with foods that have no nutrient rows reads as untracked**, although the diary has an entry.
- **Only sodium's lowered ceiling is explained on Today.** Saturated fat, free sugar and cholesterol render as `StatTile`s, which show no carry, and so does a lowered energy target.
- **The "Lowered by" note can overstate the drop.** It prints the raw negative carry, while `effective_target` clamps at the EAR.
- **A salty day's lowering can chain past two days.** A surplus is measured against the already-lowered ceiling (the spec's delta = consumed - effective target, the same rule shortfalls follow), so a day under the base ceiling but over the lowered one counts as over the limit and carries a little further, bounded by the 30% cap per source day. Measuring a ceiling's surplus against its base ceiling would stop it.
- **The Report screen's Next stops at the browser's current week**, so a browser whose clock is behind the account's timezone cannot reach the server's week in progress; the household card mirrors this.

**The planner**
- **The planner's emphasis is invisible.** `WeekPlanOut` does not carry it, so the Plan screen cannot say it is leaning on calcium because of last week.
- **Suggestions ignore oxalate.** A calcium suggestion can name a dish whose calcium comes from high-oxalate greens. The ingredient's `oxalate_class` is not used yet.
- **Suggested dishes ignore what else they carry.** On warfarin, a calcium or fibre suggestion can name a greens dish rich in vitamin K, and the next plan's calcium emphasis can lean the same way. Vitamin K has no `rda_reference` row, so it has no target. That leaves nothing to filter a dish against, and it also leaves the planner's hold-steady penalty inert in production: `_hold_steady_penalty` finds no vitamin K goal. Seeding a sourced vitamin K reference would allow both a report filter and a working penalty. The filter would drop dishes whose default portion alone moves vitamin K by more than `HOLD_STEADY_TOLERANCE` of its goal. Potassium needs no such filter: on a potassium-sparing drug it keeps its base AI, and the planner fills that AI itself.
- **Asking for next week's plan mid-week freezes a partial-week emphasis until a regenerate.** The emphasis is read from the week before the plan's, which has not finished yet; the screen only asks for the current week.

**Households**
- **Daily progress is not shared.** The spec shares "daily and weekly nutrition progress — whether each member hit their targets". The household sees only the week's counts: days logged, and nutrient-days on track out of those measured. They cover finished days only, so the card never shows whether anyone hit their targets on a particular day. Today reaches the household only once it is over, so on a Sunday the card reads zero for everyone. The sharing switch still says "Share my daily progress with the household".

**Reminders**
- **Saturday-evening plan generation is not built.** A plan generated then misses Saturday's carries, and on-demand generation on Sunday gives the same plan with them.
- **Recalibration is still re-read only on a new weigh-in.**
- **Push targets are checked for https only.** There is no allowlist of the push services' hosts.
- **A session that ends without a sign-out leaves the device subscribed** to the previous account. That covers cookie expiry and cleared cookies. The screen reads it as "on" for whoever signs in next.
- **A subscription under an old VAPID key pair reads as on but is never reminded.** Turning it off and on again fixes it.
- **Push cannot be exercised by the e2e walks.** The dev server registers no service worker. Manual spec step 16 needs a production build and VAPID keys.
- **`pywebpush` brings `aiohttp` and six small packages into the lock file.**

**Pre-existing gaps**
- **Concurrent double submits can answer 500** on the unique constraints of check-then-insert upserts: weigh-ins, cycle settings and reminder rows.
- **The swap-during-regenerate backend race remains.** The Plan screen now disables Swap and Lock while a regenerate runs.
