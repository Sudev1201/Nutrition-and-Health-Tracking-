# Closing out plan 5, and the carried-over debt

**Goal:** Finish what plan 5 left open and clear the follow-ups deferred from
plans 2.5 and 3–4, so the tracking loop has no known-wrong behaviour left in it.

**Covers:** the remainder of plan 5, plus the deferred items from
`2026-08-17-ui-foundation.md` and the known gaps in `2026-08-17-tracking-loop.md`.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`

**Status:** Complete. 309 backend tests and 193 frontend tests passing, plus 3
Playwright specs against a live API; `ruff`, `alembic check`, `oxlint`, `tsc -b`
and `vite build` all clean.

## Scope decisions taken before starting

- **Editable dish ingredients: dropped.** Plan 5's remaining named deliverable,
  removed from scope on request. It is the one item here with real architectural
  weight — where a per-entry ingredient override lives is a data-model question,
  not a UI one — so it is better done deliberately than squeezed in.
- **`drug_interaction_rules`: deferred to phase 2**, together with the rest of
  the prescription and meal-alteration work. The spec's own table lists five
  interactions and says three of them "must be re-verified against a drug
  reference during implementation before they are encoded", so there was little
  to move into a table yet.
- **Meal skipping grew from one feature into two** once it was clear that "some
  people eat four meals, some five" is a standing preference and "no time to eat,
  or I was fasting" is a fact about one day. Conflating them would have meant
  either a permanent empty slot or a preference that silently rewrote history.

## What was built

### A live data-loss bug, found while reading the code

`PUT /profile` replaces the whole questionnaire rather than merging — that is
what makes an unticked condition genuinely go away. The cost is that any field
the GET omits is destroyed by the client's next save, and `observances` was
exactly that hole on both sides of the wire: `ProfileIn` accepted vegetarian-day
rules and the service persisted them, but `ProfileOut` never returned them and
`answersFromProfile` never mapped them.

So reading a profile, editing one field and saving it back silently deleted every
saved observance. No error, nothing in the UI. Pinned now with the round trip a
profile screen actually performs.

### Four meals a day, and skipping a meal on one day

| Thing | Where it lives | Why separate |
|---|---|---|
| Eats four times, not five | `meal_slot_times.is_enabled` | A standing preference, per user, no date |
| Did not eat lunch today | `meal_slot_skips` | One day's fact, per user per date per slot |

Only the two snacks can be switched off. Four or five meals means one or two
snacks; a day without lunch is a skipped lunch, and letting a main meal be
disabled would make an unlogged one impossible to notice. The API refuses it.

A disabled slot is left out of the diary **only when that day has nothing in
it** — turning a snack off describes a normal day from now on, and hiding a real
entry from last week would be rewriting what the user ate.

Any of the five slots can be skipped. The frontend had rendered a three-way
`logged | empty | skipped` state from the start and could never receive one.

- **Skips live in their own table, not as a foodless `meal_logs` row.** Day
  totals use an empty dict to mean "nothing logged at all", and the targets
  service reads that as untracked rather than as a day of eating nothing. A skip
  in `meal_logs` would make that dict non-empty and start manufacturing
  shortfall carries. Separating them preserves the invariant by construction
  rather than by remembering to special-case it.
- **A day of nothing but skips still creates no carry.** A fast is not a debt to
  repay; a full day's shortfall would push someone to overeat for two days after.
- **Skipping is idempotent, unskipping is 204 either way.** The unique constraint
  would otherwise turn a double tap into a 500, and the toggle should not have to
  track which way round it currently is.
- **Food wins over a skip.** Logging into a skipped slot makes it `logged`.

The meal-slot vocabulary moved to `app/meal_slots.py`. It was repeated three
times — the tuple in `diary/service.py`, another in `profiles/router.py`, and the
default-times dict in `diary/router.py`.

### The baseline covers every nutrient

It already computed the whole spectrum and threw it away: `total_nutrients`
returns every code and `compute` narrowed it to `.get("energy")`, while
`resolve_day` was called for its energy row alone with every nutrient's
ear/rda/tul/kind sitting unused in the same object.

- Compared against **`rda`, not `target_effective`** — a baseline is about the
  published target, not today's ledger-adjusted one, which would make the
  starting point drift for reasons unrelated to how the person eats.
- **`off_target` is computed per `kind`, on the backend.** Below the figure for a
  target, above it for a ceiling. A single `usual - rda` sign would have told
  someone eating very little salt to eat more of it.
- The implausibility flag and its note stay energy-scoped; they are kcal
  reasoning and do not generalise.

### An unmeasured nutrient no longer reads as zero, or as a deficit

The most serious defect found. `consumed.get(code, 0.0)` turned "no food today
carried a figure for this nutrient" into a confident zero, the zero read as a
full shortfall, and for a compensable nutrient the ledger carried that shortfall
forward two days. **Measured, not theorised: 100 g of the test dish produced a
1,053 mg potassium carry into the following day off a number nothing had
measured.**

This was never iodine-specific — potassium, B12, thiamine and fibre were all
affected wherever an ingredient lacked a row. The fix is the per-nutrient
counterpart of a rule the code already stated per day: a nutrient absent from the
day's totals is skipped when planning carries.

Alongside it, `coverage` reports the share of the day's food weight that actually
carried a figure, weighted by grams so 400 g of milk with no iodine row and 10 g
of salt with one do not count equally. `dish_coverage` is the missing half of
`compute_dish_nutrients`, which inner-joins and so leaves an unmeasured
ingredient's weight in the denominator while contributing nothing to the
numerator.

- **Carries are gated on zero coverage, not on a threshold.** Choosing where
  "enough" begins would be inventing a number. Absent-versus-present is the one
  distinction the data supports, and it is exactly the confident zero that caused
  the harm. Partial coverage is reported rather than hidden.
- **A measured zero is not the same as no data.** `derived:plant-b12-zero` states
  that a plant food has no B12 — a finding, and covered. An absent row states
  nothing.

### Iodine: the gap is reported, not filled

The original instruction was to gap-fill iodine from USDA. Investigation says
that cannot be done honestly:

- USDA Foundation Foods does carry iodine (583 rows), but only ~45 distinct foods
  after de-duplicating lab sub-samples, and **none of the four marine fish the
  recipes use**. The three existing USDA iodine rows sit on ingredients no dish
  uses. Of four iodine rows in the database, only `manual:salt` reaches any dish
  — 57 of 72.
- IFCT has none: the cached CSV has 421 columns, not one matching `iod`. INDB has
  none either, and its ~1,014 fixed-value dishes can never be reached by an
  ingredient-level fill.
- USDA's dairy and egg figures reflect US iodophor sanitiser and feed-fortification
  practice, which is why this loader already refuses them and `manual:salt` takes
  its figure from FSSAI. Their 4–5× within-country spread is itself the signature
  of a production artifact rather than a compositional constant.
- Indian milk iodine values exist in the literature (≈303 µg/L, range 26–604) but
  only in paper tables, and the corroborating ICP-MS study is not Indian. No
  citable Indian figure was found, so the milk, egg and chicken rulings in
  `test_load_usda.py` stand unchanged.

So no iodine values were added. The coverage work above is what makes iodine
honest: a figure that speaks for 2% of the day now says so.

New invariants in `test_dish_coverage.py`, against the real seeded 547-ingredient
set: a dish reporting iodine must report how much of itself that figure covers,
and a salted dish must not claim its whole weight was measured. Unlike free sugar
and B12, "never reports zero iodine" is not satisfiable — there is no defensible
zero-fill — so the satisfiable invariant is that a partial figure is never
presented as complete.

### A read-only profile summary

`/profile` rendered the questionnaire itself, so there was no way to read your own
answers back, and correcting a weight meant walking all eight steps. The summary
now lives at `/profile`, the questionnaire at `/profile/:step`.

Section headings come from `STEP_ORDER` and `STEP_TITLES` rather than being
retyped. The same problem applied to the answers: the words for sex, activity,
goal, pace and diet existed only as `<option>` text inside the form, so a summary
would have restated them and been free to disagree. They are label maps in
`onboarding/types.ts` now, read by both.

404 and failure are handled differently — `useProfile` maps 404 to null, meaning
"not onboarded", which gets an empty state pointing at the questionnaire; a real
error says so rather than rendering a profile full of blanks.

### The Playwright smoke test

Deferred from plan 2.5 for a sound reason: against mocks it would assert only
that MSW returns what MSW was told. So it runs against the real backend and a
real Postgres.

**Auth is real.** The obvious route — the existing `VITE_DEMO_AUTH` handler —
does not work: it fakes `/auth/me` in the browser while the backend still has no
session, so every real endpoint answers 401. `scripts/e2e_session.py` signs a
genuine token with the app's own `create_session_token` instead.

`scripts/e2e_seed.py` runs only the ETL loaders that need no downloads —
nutrients, the transcribed ICMR rows, five real foods — so the walk works on a
database that has never pulled IFCT, INDB or USDA. That is what makes the CI job
viable; the full ETL is far too slow and network-dependent.

Two things it catches that jsdom cannot: `Sheet`'s native `<dialog>`, whose Esc
handling `setupTests.ts` says outright is verified manually; and `AppShell`
rendering both layouts into the DOM at once, so every secondary nav link exists
twice at any viewport.

## Also fixed in passing

- **CI's `npx tsc --noEmit` was checking nothing.** The root tsconfig is
  `files: []` plus project references, so without `-b` it walks an empty program
  and always passes. Type errors were only caught later by `tsc -b` inside
  `npm run build`. Now `-b`, with `tsconfig.e2e.json` bringing the specs under the
  typechecker too.
- **`WarningKind` was missing `drug-interaction`**, a kind the backend already
  emits for the potassium/ACE-inhibitor and warfarin rules, and carried
  `above-limit`, which is a per-nutrient status the backend never sends as a
  day-level warning.
- **`api.del` now takes a body**, since a skip is identified by date and slot
  rather than by an id.

## Known gaps that remain

- **Editable dish ingredients.** Dropped from scope, not solved.
- **`drug_interaction_rules`.** Deferred to phase 2 with the prescription work.
  Only the interactions the spec verified are encoded, still in code.
- **Iodine coverage itself.** Reported honestly now, but still 4 of 547
  ingredients. Closing it needs a citable Indian measurement, which this pass
  could not find.
- **Partial-coverage carries.** A nutrient measured for a small share of the day
  still generates a carry from a figure that understates intake. Gating that
  would need a threshold, and any threshold would be invented.
- **`Sheet`'s focus trap.** Esc is covered by Playwright now; the trap is not.
- **The household cooking view**, observance date ranges and one-off dates, and
  web push all remain where plan 2.5 left them.

## Verification

```
cd backend  && uv run pytest -q && uv run ruff check . && uv run alembic check
cd frontend && npm test && npx tsc -b && npm run lint && npm run build
```

End to end, with Postgres and the API running (see `frontend/README.md`):

```
cd frontend && npm run test:e2e
```
