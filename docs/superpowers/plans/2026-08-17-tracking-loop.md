# The Tracking Loop — nutrition_core, onboarding and the diary

**Goal:** Make the app usable for real: your body and conditions produce genuine
ICMR-NIN targets, you log real food from the seeded database, and the
compensation ledger actually moves tomorrow's numbers.

**Covers:** plan 3 (`nutrition_core`), plan 4 (onboarding and daily targets) and
the logging half of plan 5.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`

**Status:** Complete. 247 backend tests and 149 frontend tests passing; `ruff`,
`oxlint` and `vite build` clean.

## What was built

### `app/nutrition_core/` — pure logic, no database

| Module | Responsibility |
|---|---|
| `energy.py` | FAO/WHO/UNU 2004 BMR × ICMR's 10% body-composition correction × PAL, plus goal and pace, clamped at BMR |
| `targets.py` | Reference rows and computed macros → per-nutrient EAR / RDA / TUL |
| `conditions.py` | Condition caps and floors, conflict detection, drug interactions |
| `compensation.py` | Carry-forward arithmetic, caps, expiry, and the two clamps |

The energy formula reproduces **all six** of ICMR-NIN's published reference
figures to within 0.32% (largest miss 11 kcal on the reference man at heavy
activity). Those six are asserted directly in `tests/test_energy.py` with a
12 kcal tolerance — they are the strongest available check that the method is
right, and the residual is ICMR's own rounding.

### Persistence and API

New models in `app/models/profile.py` and `app/models/diary.py`; migration
`0ba83d174b86`. New endpoints:

| Endpoint | Notes |
|---|---|
| `GET/PUT /profile` | 404 before onboarding. A save replaces the whole questionnaire rather than merging, so an unticked condition genuinely goes away |
| `GET /profile/baseline` | What a usual day adds up to, against the computed target, with an implausibility flag |
| `POST /foods/nutrients` | Totals a list of foods. Stateless, so the wizard can show a running figure before there is a profile to attach it to |
| `GET /targets/today?date=` | Targets, warnings, `carried_in`/`carried_from` and consumed totals |
| `GET /diary?date=` | Five slots with their entries |
| `POST/DELETE /diary/entries` | Log and remove |

### Decisions worth recording

- **The ledger is derived, never stored.** `resolve_day` recomputes carries by
  walking the four days before the target date. The spec calls for an
  append-only ledger recomputable from the log; deriving it outright is the same
  guarantee with nothing to go stale, and four days is exact because a carry
  reaches at most two days forward.
- **A day with nothing logged generates no carry.** A day you did not use the
  app is untracked, not a day you ate nothing. Without this, every unused day
  would flood the next two with shortfalls the user never earned. This is not in
  the spec and is a judgement call.
- **No separate 100 kcal/decade elderly decrement.** The spec mentions one on
  top of the equations, but FAO/WHO/UNU already publishes a distinct 60+
  equation, so applying both would count the age effect twice. Only the
  published equations are used.
- **Conflicting conditions contribute *no* target changes.** Flagging while
  still applying one side's caps would be averaging by another name.

## Follow-up: preferences and the baseline

A second pass (migration `b5fee6701227`) closed the usual-intake gap and reworked
the preference lists:

- **`allergies` became `avoided_foods`.** One list covers allergies and plain
  dislikes, because the planner blocks both identically and asking someone to
  classify their own aversion as medical serves no purpose. Renamed in the
  migration rather than dropped and recreated, so existing rows survived.
- **Both preference lists take as many items as the user wants**, each optionally
  carrying a `food_id` when picked from search — which is what lets the planner
  act on a preference rather than string-matching a name against 547 ingredients.
  Free text is still accepted and marked as such in the UI.
- **`usual_intake_items` makes the baseline computable.** The step now collects
  real foods with weights instead of a free-text description, which is the whole
  reason the app could previously ask what someone eats and still not know the
  calories. A description cannot be costed against a food database.
- **An explicit `position` column** orders both lists. Neither the random-UUID
  primary key nor `created_at` could carry it — Postgres `now()` is transaction
  time, so every row saved together shares a timestamp, and the list came back
  shuffled.
- **Meal times are pre-populated** at 08:00 / 11:00 / 13:30 / 17:00 / 20:30,
  still editable.

## Follow-up: household measures

A third pass (migration `c1a2b3d4e5f6`) closed the portion gap. Logging by
household measure no longer falls back to an assumed 150 g; `ASSUMED_GRAMS` is
gone and `app/foods/measures.py` resolves the 1,022 seeded `portion_measures`
rows instead.

- **A quantity is two numbers, always.** `meal_logs` now stores the household
  measure the user chose (`measure_name`, `quantity`) alongside the absolute
  weight (`grams`), rather than one free-text label. One without the other is
  unusable: "180 g of sambar" means nothing at the table, and "half a bowl"
  means nothing to the science.
- **Drinking vessels read in ml**, because a glass of buttermilk is 250 ml to
  anyone who has ever poured one. The stored value stays grams — for
  water-based drinks the two are within a couple of percent, which is far
  inside the error of eyeballing a glass in the first place.
- **A generic measure marks the entry estimated.** When the weight behind a
  measure is a general figure rather than one measured for that particular
  food, `is_approximate` is set and the entry is flagged, so the report's
  measured-vs-estimated split stays honest.
- **Both columns are nullable.** Rows logged before the picker existed have only
  the free text, and backfilling a measure onto them would be inventing data.
- `POST /diary/entries` accepts either a measure or an explicit weight, and
  refuses a portion carrying neither.

## Known gaps

These were the gaps as this plan left them. All but the last two were closed in
`2026-08-20-plan-5-closeout.md`; see that document for what was done and for the
gaps that remain.

- ~~**The baseline uses energy only.**~~ Closed: `GET /profile/baseline` now
  returns a per-nutrient array, compared against each nutrient's published `rda`
  and respecting the target-versus-ceiling asymmetry.
- ~~**No `skipped` slot state.**~~ Closed, and wider than described here: any of
  the five slots can be skipped for a day, and a separate `is_enabled` flag
  covers eating four times rather than five.
- **Iodine coverage.** Still 4 of 547 ingredients. What changed is that it no
  longer reads as complete — a `coverage` figure now says what share of the day
  a number speaks for, and an unmeasured nutrient no longer generates a
  shortfall carry. Filling it needs a citable Indian measurement; USDA's dairy
  and egg figures reflect US practice and this loader already refuses them.
- **Drug interactions live in code**, not the `drug_interaction_rules` table the
  spec asks for. Deferred to phase 2 with the rest of the prescription work.
  Only the interactions the spec verified are encoded.
- Weight, cycle, the planner, the weekly report and reminders remain on MSW
  fixtures with their `Demo data` banners.

## Verification

```
cd backend  && uv run pytest -q && uv run ruff check .
cd frontend && npx vitest run && npm run build && npm run lint
```

Manual, with Postgres and both servers running: sign in, complete onboarding,
and confirm Today shows roughly 2,110 kcal for a 25-year-old 65 kg sedentary
man. Log a meal from the real food search and watch the totals move. Log a small
meal dated yesterday and confirm today's calcium target rises while protein's
does not.
