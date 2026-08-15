# South Indian Nutrient Tracker — Design & Implementation Plan

## Context

You want a web application that tracks macronutrients and micronutrients (vitamins and
minerals) for a South Indian diet. The problem it solves: generic nutrition apps are built
around Western foods, treat every nutrient as a hard daily target, and ignore that a
shortfall today can legitimately be made up over the following days — for some nutrients
but not others.

This app:

- Learns your body, health situation and eating habits before suggesting anything.
- Computes personalized daily targets from Indian reference values (ICMR-NIN 2020), not US ones.
- Carries a shortfall forward into the next 2 days **only for nutrients the body can actually buffer**.
- Generates a customizable 7-day South Indian meal plan every week, and re-plans the rest of
  today whenever you eat something different from the plan.
- Tracks weight weekly and adjusts calorie targets when the trend drifts from your goal.
- Respects vegetarian observance days, medication timing, and restaurant meals as facts of a
  real week rather than exceptions.
- Reports weekly on what you hit, what you missed, and what to eat next week.

`/Users/sudev-20602/Sudev/healthMonitor` is currently empty — this is a greenfield build.

### Decisions already made

| Decision | Choice |
|---|---|
| Platform | Responsive web app — works on phone and desktop alike |
| Users | Multiple (family/friends), each with own profile |
| Auth | Google sign-in only |
| Stack | React frontend + Python FastAPI backend + Postgres |
| Food logging | Dishes with editable ingredients; household measures, grams optional |
| Meal planning | Deterministic algorithm; optional LLM polish when user supplies own API key |
| Health scope | Type 2 diabetes/prediabetes, high cholesterol, high & low BP, thyroid — with lab values, and **medications captured for every condition** |
| Meal slots | 5 per day: breakfast, snack 1 (mid-morning, optional), lunch, snack 2 (evening), dinner |
| Language | English only for dish and ingredient names |
| Sharing | Households: shared custom dishes, members can see each other's progress |
| Observance | Per-weekday and seasonal vegetarian days are a first-class constraint |
| Cycle | Women's profiles can track the menstrual cycle and adapt the plan |
| Eating out | Restaurant and western food logged through the same diary, marked as estimated |
| Reminders | Preferred meal times collected at onboarding; browser push in phase 1, WhatsApp logging and queries in phase 2 |
| Week | Sunday to Saturday; plan generated Saturday evening, report closes Saturday night |
| Scope | Full product built in one project (internally sequenced milestones) |

**Beverages are first-class.** The evening snack slot in particular comes with tea or coffee,
and milk coffee is nutritionally significant — it carries calcium, added sugar, and caffeine.
Each snack slot therefore accepts a paired beverage entry, and the sugar and milk in it count
toward the daily totals. This also matters medically: milk coffee is exactly the thing that
must not be taken within 60 minutes of levothyroxine.

---

## Research Foundation

Three research passes over primary sources produced the science this app encodes. Full
citations live in the design doc written during implementation; the load-bearing findings:

### Nutrient compensability (drives the 2-day carry-forward rule)

The DRI framework itself states reference intakes are *"average daily intake over 1 or more
weeks"* — this is what makes multi-day compensation scientifically valid at all. But the
buffer differs per nutrient:

- **Compensable (2-day carry-forward valid)** — energy, fats/essential fatty acids, vitamins
  A, D, E, B12, folate, C, B1, B2, B3, B5, B6, biotin, and minerals iron, calcium, magnesium,
  iodine, selenium, copper. Every one has a body store of a week or more; B12 has years.
- **NOT compensable** — **protein**: there is no storage pool, and a 12-day human trial found
  no catch-up effect for insufficient amino-acid intake. Excess is oxidized, not banked.
  Deficit expires at midnight; per-meal distribution matters instead.
- **Partially compensable** — **vitamin K** (liver stores drop to ~25% in 3 days → 1-day
  carry only), **fiber** (long-run benefit averages, but doubling in a day causes GI distress
  → carry capped at ~25% of the daily target).
- **Never carried up** — **sodium**: a sodium "deficit" is not a thing to compensate.

### Harmful-surplus rules (drives downward compensation)

Reduce the next days' targets only when a surplus is genuinely storable and harmful in
excess: **sodium, energy, vitamin A, vitamin D, iron, selenium, iodine** (plus copper, zinc,
calcium at supplement-level intakes). Water-soluble vitamin surpluses are excreted — nothing
to rebalance, so no downward compensation. A single massive overdose (e.g. iron supplements)
raises a **warning**, never a silent rebalance.

### Condition rules (all quantitative and citable)

- **Type 2 diabetes / prediabetes** — fiber ≥14 g per 1,000 kcal (RSSDI: 25–40 g/day); added
  sugar ≤25–30 g/day; carbs 50–60% of calories; partial white-rice substitution with
  millets/brown rice; pair idli/dosa with sambar/dal/egg for protein. Glycemic index is a *soft
  preference* — ADA's evidence review found no consistent A1C effect.
- **High cholesterol** — saturated fat <7% of calories (strict tier 5–6%); trans fat ~0;
  dietary cholesterol <200 mg; viscous fiber 5–10 g/day. Lipid Association of India explicitly
  says avoid coconut oil and palm oil → this is the central South Indian conflict: cap coconut
  oil, thick coconut-milk gravies, ghee, and deep-fried vada/murukku.
- **Hypertension** — sodium tightened to <1,500 mg; potassium 3,500–5,000 mg from food;
  DASH food-group pattern. High-sodium South Indian flags: pickles, appalam/vadam, karuvadu,
  salted buttermilk, chutney podis, store-bought sambar powders. The potassium half of this
  advice is **conditional on medication** — see the drug-interaction table under the planner.
- **Hypotension (symptomatic/orthostatic only)** — fluid 2–3 L/day, salt 6–10 g NaCl/day,
  smaller frequent meals, avoid large carb-heavy single meals. Evidence graded low-quality.
- **Hypothyroidism** — the highest-value rules are **medication timing**: levothyroxine on an
  empty stomach ≥60 min before any food *including milk coffee*, and ≥4 h away from calcium
  and iron. Iodized salt yes; iodine supplements no. Cooked cruciferous vegetables are fine.
  TSH is the control variable; uncontrolled hypothyroidism lowers resting energy expenditure.
- **Hyperthyroidism** — avoid excess iodine; raised calorie and protein needs until euthyroid;
  ensure calcium + vitamin D for bone protection. Supports a temporary low-iodine
  (<50 µg/day) mode for the 1–2 weeks before radioiodine treatment.

**Conflict handling is mandatory:** hypertension and hypotension give opposite sodium
instructions. The engine must detect conflicting condition pairs and surface a
"consult your clinician" flag rather than silently averaging targets.

**Two reconciliations to get right**, because the US and Indian numbers overlap:

- *Sodium.* The ICMR baseline of ~2,000 mg (5 g salt) is already stricter than the US
  <2,300 mg that the diabetes and general guidelines cite, so the baseline satisfies them
  outright. Only hypertension moves the number, tightening it to 1,500 mg. There is no case
  where a condition should *raise* sodium above the ICMR ceiling except diagnosed symptomatic
  hypotension — which is exactly why that pair is a flagged conflict.
- *Fiber.* ICMR's baseline of 30 g per 2,000 kcal equals 15 g per 1,000 kcal, which already
  clears the ADA's ≥14 g per 1,000 kcal for diabetes. So diabetes does not raise the
  per-calorie fiber target; it applies RSSDI's absolute 25–40 g/day band as a floor and pushes
  fiber-dense food choices in the planner instead.

### Food data sources (this de-risks the biggest unknown)

1. **INDB — Indian Nutrient Databank** (Anuvaad Solutions): 1,095 food items **plus 1,014
   Indian recipes with ingredient amounts, cooked weight, servings, and serving sizes**.
   Open access Excel download, peer-reviewed methods paper, built on IFCT 2017. This is
   almost exactly the dish→ingredient mapping the app needs — it becomes the seed.
2. **IFCT 2017** (ICMR-NIN): 528 foods × 151 nutrients including full fatty-acid profiles and
   individual sugars — needed for the saturated-fat and diabetes rules. Official release is
   PDF-only; unofficial machine-readable CSV mirrors exist on GitHub. No formal open license
   ("dissemination encouraged"), so it is fine for personal/family use; commercial
   distribution would need written permission from NIN.
3. **USDA FoodData Central** (CC0, bulk CSV + API) — gap-filler for foods IFCT lacks
   (oats varieties, olive oil, packaged goods) and for iodine values.

Every food row is **source-tagged**, because IFCT and USDA use different carbohydrate and
fiber conventions and must be normalized before mixing.

**Sourcing status:** the full 319-page ICMR-NIN 2020 report is paywalled (₹400), but NIN
publishes a free authoritative extract ("A Brief Note on Nutrient Requirements for Indians")
containing the energy, protein and 14-nutrient tables verbatim. The ICMR Tolerable Upper Limit
report is a scanned image PDF with no text layer, so its values must be transcribed visually
and each one verified in a second pass. Every seeded row records its source.

### Indian reference values (ICMR-NIN 2020) — findings that change the design

- **ICMR explicitly recommends EAR, not RDA, for planning an individual's diet.** The app
  therefore uses both: RDA as the daily target shown to the user, EAR as the adequacy floor
  below which a shortfall is real. This is what gives the compensation engine a principled
  lower bound.
- **The B vitamins scale with activity, and the widely-quoted "ICMR RDA" numbers are the
  *moderate*-activity column.** Thiamine, riboflavin, niacin and B6 are energy-scaled — using
  the headline figures for a sedentary user over-targets by roughly 25%. The seed table must be
  activity-indexed for these four.
- **Energy formula, verified by reconstruction**: `TEE = FAO/WHO/UNU 2004 BMR(age, sex, weight)
  × 0.90 (men) or 0.91 (women) × PAL`, with PAL = 1.40 sedentary / 1.80 moderate / 2.30 heavy.
  ICMR-NIN 2020 does **not** use Henry equations; it applies a cumulative 10% downward
  correction to FAO/WHO/UNU because Indian body composition carries relatively more fat. This
  formula reproduces all six of ICMR's published energy figures to within their stated
  rounding, and generalizes to the user's actual weight as the report instructs.
- **Protein has a South-India-specific catch.** EAR 0.66 g/kg/day, RDA 0.83 g/kg/day — but
  ICMR footnotes that *"for people consuming cereal-based diet with low quality protein, the
  protein requirements are 1 g/kg per day."* A rice-dominant diet without adequate pulses and
  milk is exactly that case, so the app ships a **diet-quality toggle** switching the protein
  target between 0.83 and 1.0 g/kg. The 0.83 figure assumes a cereal:legume:milk ratio of
  3:1:2.5, which the planner can actively steer toward.
- **Salt: use the ICMR ceiling of 5 g salt/day (~2,000 mg sodium) *inclusive of invisible
  salt*,** not the US 2,300 mg figure. It is stricter, locally intended, and explicitly counts
  the sodium hidden in pickles, appalam and salted snacks — which is precisely where South
  Indian sodium comes from.
- **Indian TULs exist** for iron 45 mg, zinc 40 mg, calcium 2,500 mg, iodine 900 µg, vitamin A
  3,000 µg, vitamin D 4,000 IU, vitamin E 1,000 mg, niacin 35 mg, B6 100 mg, folate 1,000 µg,
  vitamin C 2,000 mg. ICMR **declined to set** a limit for thiamine, riboflavin, biotin, B12
  and potassium — so the app raises no food-based surplus warning for those.
- **Magnesium's 350 mg upper limit is for supplements only and explicitly excludes food and
  water.** Warning on dietary magnesium would be a bug.
- **Age matters beyond calories.** At 60+, calcium rises to 1,200 mg and vitamin D to 800 IU
  while protein stays fixed and energy falls sharply — so the required *protein density* of an
  elderly diet rises about 24%. Energy declines a further 100 kcal/decade (men) and
  70 kcal/decade (women), implemented as a continuous decrement rather than a step.
- Reference weights are 65 kg (man) and 55 kg (woman). Reference *heights* could not be
  verified against any primary source and are not needed — the energy equations are
  weight-based — so they must not be hard-coded.
- Also new in 2020 and worth tracking: a **carbohydrate minimum of 100–130 g/day** and
  **fiber at 30 g per 2,000 kcal**.

Two caveats to surface in the app: FSSAI states the upper-limit report is *"only for
information and NOT for use ... for regulatory purpose"* — it is sound science, not a legal
limit. And pregnancy is an explicit exception to the iron ceiling, since supervised
supplementation deliberately exceeds it.

---

## Architecture

Two deployable services plus a managed database.

```
React (Vite + TS)  ──HTTPS──>  FastAPI (Python)  ──>  Postgres
  static hosting                container host          managed
       │                              │
       │                              ├── nutrition_core   (pure domain logic, no DB)
       │                              ├── planner          (deterministic + optional LLM polish)
       └── Google Identity ──────────>└── auth (verifies Google ID token, issues session)
```

- **Frontend**: React + TypeScript (Vite), responsive from a phone up to a desktop monitor —
  the same codebase, with the daily dashboard and weekly report laying out in multiple columns
  on a wide screen rather than being a stretched phone view. TanStack Query for server state,
  Tailwind for styling, Recharts for weekly report charts.
- **Backend**: FastAPI + SQLAlchemy + Alembic. Python chosen because the meal planner benefits
  from real optimization tooling (OR-Tools / SciPy) and the nutrient math is easier to test there.
- **Database**: Postgres (Neon or Supabase free tier).
- **Hosting**: frontend on Cloudflare Pages/Vercel, backend container on Fly.io/Railway, both
  behind one custom domain.
- **Seed data**: offline ETL scripts (`etl/`) that ingest INDB + IFCT + USDA into versioned
  seed tables. Run once, committed as reproducible scripts, not hand-typed data.

### Backend module boundaries

Each module has one purpose and is independently testable. `nutrition_core` is pure functions
over plain data structures — no database, no HTTP — which is what makes the science testable.

| Module | Responsibility |
|---|---|
| `auth/` | Google ID token verification, session cookie, user record |
| `households/` | Household creation, invites, membership, per-user visibility settings |
| `profiles/` | Onboarding questionnaire, anthropometrics, conditions, thyroid labs/meds, favorites, allergies |
| `nutrition_core/energy.py` | BMR → TDEE from ICMR-NIN methodology; goal-based calorie adjustment |
| `nutrition_core/targets.py` | ICMR-NIN reference tables → personalized per-nutrient daily targets |
| `nutrition_core/conditions.py` | Condition rule engine: caps, emphases, conflict detection |
| `nutrition_core/compensation.py` | Nutrient classification + carry-forward ledger math |
| `foods/` | Ingredients, dishes, recipe composition, portion measures, user-custom dishes |
| `diary/` | Per-meal logging, gram resolution, plan-deviation detection |
| `planner/` | 7-day plan generation, intra-day re-plan, swap suggestions, LLM polish adapter |
| `weight/` | Weigh-ins, trend smoothing, calorie recalibration |
| `cycle/` | Cycle and symptom logging, symptom-driven coaching rules |
| `reminders/` | Meal-slot scheduling behind a channel interface (web push now, WhatsApp later) |
| `reports/` | Weekly aggregation, adherence, gap analysis, next-week suggestions |

---

## Core Engines

### 1. Target computation

Personalized daily targets are derived per user, not looked up from a static table. Each
nutrient carries three numbers: an **EAR floor**, an **RDA target**, and a **TUL ceiling**.

1. **Energy** — `BMR(FAO/WHO/UNU 2004, age+sex+weight) × 0.90 or 0.91 × PAL(1.40/1.80/2.30)`,
   then adjusted for the user's goal and chosen pace. Age 60+ applies the per-decade decrement.
2. **Macros** — protein at 0.83 g/kg, or 1.0 g/kg when the diet-quality toggle marks a
   cereal-dominant low-quality-protein diet; fat and carbohydrate as percentage-of-energy bands
   with a 100–130 g/day carbohydrate floor; fiber at 30 g per 2,000 kcal.
3. **Micros** — ICMR-NIN EAR/RDA/AI by age and sex, with thiamine, riboflavin, niacin and B6
   selected from the **activity-matched** column rather than the headline moderate figures.
4. **Condition overlay** — caps and floors applied (e.g. sodium tightened to 1,500 mg for
   hypertension; saturated fat capped at 7% of calories for dyslipidemia; an absolute
   25–40 g/day fiber floor for diabetes). Conflicting conditions flagged rather than averaged.
5. **Clamp** — every target clamped between its EAR floor and its TUL ceiling, using the Indian
   TUL where ICMR defines one, a clearly source-tagged IOM/EFSA value where it does not, and no
   ceiling at all for the nutrients ICMR deliberately left open.

### 2. Compensation ledger

An append-only ledger, fully recomputable from the log — never a mutated running total, so it
is idempotent and testable.

On day close (in the user's timezone), for each nutrient:

```
delta = consumed − effective_target

if delta < 0 and nutrient is COMPENSABLE_UP:
    split the deficit 50/50 across the next 2 days
    cap each day's increase at 30% of that day's base target   (fiber 25%, vitamin K 1 day only)
    anything beyond the cap expires → recorded as "uncompensated" in the weekly report

if delta > 0 and nutrient is EXCESS_SENSITIVE:
    reduce the next 2 days' targets, same capping
    never reduce below the nutrient's EAR floor

if delta > 0 and nutrient is water-soluble / not excess-sensitive:
    do nothing — surplus is excreted

protein and a sodium shortfall never carry forward at all
never let an adjusted target exceed the Tolerable Upper Limit
single-day intake far above UL → warning surfaced, no silent rebalance
```

### 3. Meal planner

Runs at the start of each week — generated Saturday evening for the Sunday-to-Saturday week
ahead — and again for the remaining slots of a day when you log something off-plan.

1. **Filter** — candidate dishes per meal slot (idli/dosa are breakfast, not dinner-rice at
   7am), removing allergens, diet-type violations, and condition hard-blocks. Snack slots also
   propose a paired beverage; the mid-morning snack may be left empty on any day.
2. **Greedy construction** — score each candidate on how much it closes the remaining
   weighted nutrient gap, plus a favorite-ingredient bonus, a repetition penalty, and
   condition soft-penalties. Slight randomization keeps weeks from being identical.
3. **Portion tuning** — scale servings within realistic bounds to close macro gaps.
4. **Local search** — repeatedly swap the worst-contributing dish for a better alternative
   until the weighted gap stops improving.
5. **Optional LLM polish** — only if the user has supplied their own API key: rewrites
   descriptions and adds cooking notes for *already-chosen* dishes. It never changes a dish,
   a portion, or a nutrient number.

The weekly plan is fully customizable: swap a dish (the app ranks alternatives that keep the
day feasible), lock meals you have already decided on, or regenerate a single day.

**Medication is a planner constraint, not a note.** Onboarding records the medications for
every condition, not just thyroid, because several of them change what the planner may
suggest and when:

| Medication | Effect on the plan |
|---|---|
| Levothyroxine | First food or beverage of the day — *including milk coffee* — scheduled ≥60 min after the dose, checked against the breakfast time in the profile; calcium- and iron-heavy items (curd, ragi, milk, supplements) kept ≥4 h away |
| ACE inhibitor / ARB / potassium-sparing diuretic | **Suppresses the potassium-loading advice** that hypertension would otherwise trigger. Raising potassium is actively unsafe on these drugs; the app flags it for clinician review instead of pushing coconut water and banana |
| Warfarin | **Disables vitamin K compensation entirely.** The goal on warfarin is day-to-day *consistency* of vitamin K, not averaging — so the planner holds vitamin K steady instead of swinging it |
| Metformin | Dose paired with a meal rather than an empty slot, to reduce GI upset |
| Statin | Grapefruit flagged (a genuine interaction, though rare in this cuisine) |

The levothyroxine timing rules and the potassium-with-ACE-inhibitor caution are both directly
sourced from the guideline research. The remaining interactions must be re-verified against a
drug reference during implementation before they are encoded — and the medication list is
stored as data in a `drug_interaction_rules` table so it can be extended without code changes.

**Deviation handling** — logging something different from the plan re-plans only the remaining
slots of *that day*. The rest of the week is untouched unless you ask for a regeneration.

### 4. Weight-driven adjustment

Weekly weigh-in compared against the expected trajectory for your goal, smoothed over the last
2–3 weigh-ins so water-weight noise doesn't cause thrash. Sustained drift adjusts the calorie
target by a bounded step (±10% max), clamped so it never falls below BMR or a safe absolute
floor. Macros recompute from the new calorie figure, and so do the nutrients that are
energy-scaled by ICMR's own method — fiber, thiamine, riboflavin, niacin and B6. The remaining
micronutrients stay RDA-anchored, since they don't move with calorie intake. Protein is
weight-based, so it follows measured weight rather than the calorie target.

### 5. Baseline intake discovery at signup

Most people don't know their current calorie intake, so onboarding never asks for it. Instead
it offers a **usual-intake wizard**: you describe what you normally eat at each of the five
slots — the everyday idli-and-sambar breakfast, the usual lunch, the evening tiffin — and the
app computes your current baseline from the food database.

That baseline is not the target; the target still comes from the ICMR energy formula. The
baseline's job is to show the gap between what you eat now and what you need, so the first
week's plan is a realistic step from where you actually are rather than an abrupt jump. It also
catches a bad profile early: if the computed intake and the computed requirement are wildly
apart, that is worth surfacing before generating a plan.

### 6. Diet observance rules

Many South Indians skip non-vegetarian food on particular days, and the pattern is personal —
some avoid it on Tuesdays and Fridays, some on Saturdays, some through the whole of Purattasi
or on specific festival and fasting days. The planner treats this as a **hard constraint**, not
a preference:

- **Recurring weekday rules** — e.g. "vegetarian on Tuesday, Friday, Saturday".
- **Date-range observances** — e.g. an entire month such as Purattasi, or a fasting period.
- **One-off dates** — a specific festival or a personal observance.

On an observance day, **egg counts as non-vegetarian and is excluded** along with meat and
fish. That makes these days genuinely harder for protein and B12, which is precisely why the
planner leans on dairy, legumes and the cereal:legume:milk ratio to hold protein up.

The planner respects these when generating the week and when re-planning a day, and the
compensation engine is what keeps this from costing nutrition: a run of vegetarian days that
pushes B12 or iron down gets made up in the days that follow, within the caps that already
exist. Observance days therefore change *what* is suggested, never *whether* targets are met.

### 7. Eating out and non-Indian food

Real weeks include restaurant meals and western food, so the diary is not restricted to the
South Indian catalogue. Logging searches the full database — the South Indian dishes, the
wider Indian set, and USDA FoodData Central including its branded/packaged foods — and entries
logged this way are **marked as estimated**, since a restaurant portion is a guess.

That flag matters downstream: the weekly report separates measured from estimated intake, so a
week that was largely eaten out is not presented with false precision. The planner also learns
from it — if you routinely eat out on a particular day, it can plan lighter around it rather
than pretending the meal didn't happen.

When something isn't in any database, the app does **not** offer a calories-only quick add.
It walks you through composing the item from ingredients it does know — rough amounts are
fine — and saves the result for next time. A calorie-only entry would look like a logged meal
while reading as zero for every vitamin and mineral, which would quietly poison the
compensation ledger and the weekly report. Composing from ingredients costs a minute once and
keeps every nutrient accounted for, and the database gets better the more you use it.

### 8. Menstrual cycle awareness

Cycle tracking is optional, off unless enabled, and private by default within a household. A
dedicated research pass over the primary literature settled what it should and shouldn't do —
and the obvious features turned out to be the wrong ones.

**Two things the app must NOT do, despite being the intuitive design:**

- **Never raise the iron target during menstruation.** ICMR's 29 mg/day for women (vs 19 mg for
  men) *already* averages menstrual blood loss across the whole cycle — the IOM states this
  verbatim, and ICMR's derivation is the same. The giveaway is that ICMR's *pregnancy* iron RDA
  (27 mg) is **lower** than the non-pregnant one, which only makes sense if menstruation is
  baked into the 29. Spiking iron on bleed days double-counts the same loss. It is also futile:
  offsetting the loss in real time would need roughly 37 mg of *extra* dietary iron per day at
  8% absorption. The body already handles it — hepcidin falls during menses, raising absorption
  automatically.
- **Never adjust calorie targets by cycle phase.** The luteal increase in resting expenditure is
  real but tiny: about +37 to +105 kcal/day, falling to ~32 kcal/day expected once you account
  for the ~37% of cycles that are anovulatory, and it vanishes entirely in hormonal
  contraceptive users. That sits inside a ±500 kcal/day day-to-day intake variation and a
  360+ kcal/day systematic under-reporting bias. The one RCT of a cycle-adapted weight-loss
  programme was null on intention-to-treat. There is also a self-fulfilling trap: telling users
  the app expects them to eat more in the luteal phase manufactures exactly the logging pattern
  that would appear to validate the feature.

**What the app does instead — the evidence-backed version:**

| Feature | Rule | Evidence |
|---|---|---|
| **Coffee/tea timing** | Move filter coffee or tea at least 1 hour away from meals. In young Indian women specifically, one cup of tea with a rice meal cut iron absorption ~49%, two cups ~67%; a 1-hour gap roughly halves the inhibition | Strong, and directly South Indian |
| **Vitamin C pairing** | Around menstruation, prompt iron-rich meals paired with lemon, tomato, tamarind, amla or guava — coaching changes, the target number never does | Mechanistic, sound |
| **Calcium as the flagship** | Target 1,000–1,200 mg/day; it is the *only* nutrient both ACOG and RCOG endorse for PMS, and typical Indian women's intake is ~270–500 mg/day. Set expectations honestly: the trial took 3 cycles to show benefit | Moderate; guideline-endorsed |
| **Ginger (sukku) for cramps** | 750–2,000 mg/day of dry ginger powder, days 1–3 of menses only, offered as a *measured* quantity | Moderate — comparable to mefenamic acid and ibuprofen in head-to-head trials |
| **Fenugreek (methi) seed** | 2.7–4 g/day of seed powder, days 1–3, over 2 cycles | One RCT; labelled low-quality |
| **Heavy bleeding** | Validated symptom questions (soaking a pad in ≤2 h, bleeding >7 days, clots, flooding) trigger a **clinician referral**, never a nutrient-target change | Guideline-driven; ~20% of adolescents with heavy bleeding have an underlying bleeding disorder, so responding with dietary advice would suppress a real referral signal |
| **Symptom-driven, not calendar-driven** | Only 13% of cycles are actually 28 days, and the follicular phase ranges 10–30 days — so logged symptoms, not a predicted phase, drive any individualisation | — |

**Two food-database corrections this research forces**, both of which matter beyond the cycle
feature:

- **"All keerai is calcium" is wrong.** Arai/mulai keerai, palak and colocasia leaves are very
  high in total oxalate — calcium absorption from spinach is about 5%, against 28–32% from
  milk. Murungai keerai, curry leaf, methi leaf and coriander carry only insoluble oxalate and
  are genuinely usable. The database must carry this distinction rather than crediting all
  greens equally.
- **Ragi is the best calcium vehicle and one of the worst iron vehicles** — 364 mg calcium per
  100 g with ~23% retention, but only 4.6% iron absorption from a ragi-dal-greens meal because
  of phytate. Whole and hulled sesame must also be separate entries, since the calcium lives in
  the hull.

**Postmenopausal users are a real gap that must be handled explicitly.** ICMR-NIN 2020 publishes
no postmenopausal category, so applying the 29 mg/day figure would substantially overstate the
requirement for a woman who no longer menstruates — and there is no route of iron excretion.
The app falls back to the IOM value (8 mg/day) with a visible note that a different framework is
being used, and flags intakes approaching the 45 mg/day upper limit.

One UI caution carried over from the research: the perimenstrual **chocolate craving script is
largely an American cultural artefact** — endorsement runs 17% among foreign-born women versus
41% among second-generation immigrants, and cravings don't track measured intake anyway. It has
no place in an Indian product's copy.

### 9. Reminders

The whole design rests on you logging after every meal, so reminders are load-bearing rather
than a nicety — an app that depends on daily logging and doesn't reach out is an app that goes
quiet in week three.

**Meal times are collected at onboarding.** Each of the five slots gets the user's usual time —
breakfast at 8, lunch at 1, evening tiffin at 5, and so on — because everyone's day is
different and a reminder at the wrong hour is worse than none. Times are editable later, and
can differ between weekdays and weekends, since a Sunday breakfast rarely happens at 8am.

These times do double duty. They drive the reminders, and they make the medication windows
concrete: knowing that levothyroxine is taken at 7am and breakfast coffee is at 8am is what
lets the planner check the 60-minute gap rather than assume it.

**Phase 1 — browser push.** Permission is requested once, then a push fires at each slot's
time if nothing has been logged for it, linking straight into that slot's logging screen. Web
push works with the tab closed and needs no app store. Reminders can be silenced per slot — the
optional mid-morning snack shouldn't nag someone who rarely eats it — and the app stops
reminding once a slot is logged.

**Phase 2 — WhatsApp.** A WhatsApp integration lets you log a meal by replying in the chat and
ask what's left for the day without opening the app at all — the most natural interface for
this in India. It is deliberately deferred: it needs a WhatsApp Business API account, a verified
number, approved message templates, and a webhook service, none of which should block the core
product. The reminder layer is therefore built behind a **channel interface** from the start, so
adding WhatsApp later is a new adapter rather than a rework.

---

## Households & Privacy

A user can create a household and invite others by email link; each person still signs in with
their own Google account and keeps their own profile, targets, and plan.

- **Shared automatically**: custom dishes. A recipe one person enters is available to everyone
  in the household, so home recipes are entered once.
- **Shared by default, toggleable off**: daily and weekly nutrition progress — whether each
  member hit their targets. This is what makes the household view useful to whoever cooks.
- **Private by default, opt-in to share**: health conditions, thyroid labs, medications, and
  weight. These are sensitive and never exposed without the member explicitly enabling it.

Because the household usually eats the same food, the planner offers a **cooking view**: for a
given meal slot it shows where members' planned dishes coincide, so one dish can be cooked once
and portioned differently per person rather than cooking separate meals.

## Data Model

Reference/seed tables (shared): `nutrients`, `ingredients`, `ingredient_nutrients`,
`dishes`, `dish_ingredients`, `portion_measures`, `rda_reference`, `upper_limits`,
`condition_rules`, `drug_interaction_rules`.

Per-user tables: `users`, `profiles`, `health_conditions`, `thyroid_labs`, `medications`,
`favorite_ingredients`, `allergies`, `observance_rules`, `meal_slot_times`, `meal_logs`,
`daily_targets`,
`compensation_ledger`, `weight_logs`, `cycle_logs`, `cycle_symptoms`, `meal_plans`,
`meal_plan_items`, `weekly_reports`, `push_subscriptions`, `user_settings`.

Household tables: `households`, `household_members`, `household_invites`.

Notes:
- Nutrients stored **long-format** (`ingredient_nutrients` rows), not 150 columns.
- `ingredients.source` tags IFCT / USDA / INDB so conventions can be normalized.
- `dishes` carries a nullable `household_id` — null means a curated seed dish, set means a
  dish someone in that household created, shared with all its members.
- `compensation_ledger` rows record `source_date`, `applies_to_date`, `amount`, `capped`,
  `expired` — so the weekly report can honestly show what could not be made up.
- `observance_rules` covers all three shapes with one table: a recurring weekday, a date range,
  or a single date.
- `meal_logs.is_estimated` marks restaurant and eyeballed portions so reports can separate
  measured from approximate intake.
- `ingredients` needs an **oxalate class** and a whole-vs-hulled distinction, so the calcium
  math for greens and sesame is honest rather than crediting raw composition figures.
- `meal_slot_times` holds a time and a reminder-on flag per slot, with an optional weekend
  variant — this is what both the reminder scheduler and the medication-window checks read.
- LLM API keys in `user_settings` stored encrypted at rest.

---

## Prerequisite: Google OAuth client

Google sign-in is the only way into the app, so a Google OAuth client must exist before the
frontend can authenticate anyone. This is a one-time console setup, not code.

**Create the client** at [console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients)
→ *Create client* → application type **Web application**.

**Authorised JavaScript origins** — add **both** of these for local development:

```
http://localhost
http://localhost:5173
```

Google matches the origin as scheme plus fully-qualified hostname only: no path, no trailing
slash. Both entries are needed because the bare `http://localhost` and the port-qualified form
are treated as distinct origins. The production domain gets added here later, over HTTPS.

**Authorised redirect URIs** — leave empty. The app uses the Google Identity Services
JavaScript callback, which hands the ID token to our own code; redirect URIs only matter for
the server-side authorization-code flow, which this design does not use.

**The client secret is not needed and must not be deployed.** The backend verifies the ID token
by checking its signature and audience against the client ID
(`verify_oauth2_token(token, request, client_id)` in `app/auth/google.py`). Nothing in this
architecture ever exchanges a secret with Google. The console will offer one; ignore it.

**Consent screen and who can sign in.** Under the Audience settings, an app with *Testing*
publishing status only admits Google accounts explicitly listed as test users (up to 100),
which is the right setting for family and friends. Because the app requests only the basic
`openid`, `email` and `profile` scopes — none of which are sensitive or restricted — moving to
*In production* later does not require Google's verification review; it only needs the branding
fields (app name, support email, homepage, privacy policy) filled in.

**Where the client id goes.** The same value in two places, since the frontend requests the
token and the backend verifies it:

| File | Variable |
|---|---|
| `frontend/.env.local` | `VITE_GOOGLE_CLIENT_ID` |
| `backend/.env` | `GOOGLE_CLIENT_ID` |

The value looks like `1234567890-abc123def456.apps.googleusercontent.com`. Both files are
git-ignored.

**A likely snag for this project:** creating Cloud projects can be blocked by Workspace
organisation policy on a corporate account. If `sudev.g@zohocorp.com` cannot create a project,
use a personal Google account for the console — the OAuth client works the same, and the
accounts that *sign in* to the app are independent of the account that owns the client.

---

## Implementation Sequence

Built as one project; this is the order that keeps the app runnable at every step.

0. **Google OAuth client** — the one-time console setup described above. Nothing in step 2
   works without it, though steps 1 and 3 do.
1. **Foundation** — repo scaffold (backend + frontend + docker-compose Postgres), Alembic
   setup, CI running tests.
2. **Auth & households** — Google sign-in end to end, session handling, protected routes,
   household creation/invites and visibility settings.
3. **Food & reference data ETL** — ingest INDB recipes + IFCT ingredients + USDA gap-fillers
   into seed tables; normalize units and conventions; verify a sample of dishes by hand against
   the published tables. Also seed `rda_reference` (EAR, RDA/AI, activity-indexed for the four
   energy-scaled B vitamins) and `upper_limits` from ICMR-NIN 2020, falling back to
   source-tagged IOM/EFSA values where ICMR defines none, and leaving genuinely open-ended
   nutrients without a ceiling. Every value transcribed from the scanned TUL report gets a
   second verification pass.
4. **`nutrition_core`** — energy, targets, condition rules, compensation. Pure logic, TDD, no
   API surface yet. This is the scientific heart and gets the heaviest test coverage.
5. **Onboarding** — the profile questionnaire (anthropometrics, activity level, goal + pace,
   conditions, thyroid labs, medications and their dose times for **every** condition, diet
   type, protein-quality of the usual diet, allergies, favorite ingredients as individual items
   like curd/milk/apple, observance rules for vegetarian days, and the usual time of each of the
   five meal slots), producing a first set of daily targets. Includes the usual-intake wizard so
   users who don't know their current calorie intake can have it computed from the foods they
   normally eat. Once enough days are logged,
   the app can re-derive protein quality from the actual cereal:legume:milk ratio instead of
   relying on the self-assessment.
6. **Logging + daily dashboard** — log meals by dish with household measures (grams optional),
   edit a dish's ingredients, log restaurant and western food from the wider database as
   estimated entries, see today's targets vs consumed and carried-forward adjustments.
7. **Planner** — 7-day generation honouring observance days and medication timing,
   customization/swap/lock, intra-day re-plan on deviation, household cooking view.
8. **Weight tracking** — weigh-in entry, trend chart, automatic calorie recalibration.
9. **Cycle tracking** — optional cycle and symptom logging, the coffee/tea timing and
   vitamin-C pairing coaching, calcium emphasis, and the heavy-bleeding referral prompt.
10. **Weekly report** — intake vs target per nutrient, adherence, uncompensated gaps, measured
    vs estimated split, next week's suggested foods, feeding into the next plan.
11. **Reminders** — web push at meal slots, behind a channel interface.
12. **Optional LLM polish** — BYO API key setting and the polish adapter.
13. **Deploy** — domain, both services, managed Postgres, seed data migration.
14. **Phase 2: WhatsApp** — log a meal and query the day's remaining slots from chat, added as
    a second reminder channel.

---

## Testing & Verification

**Automated**
- `pytest` over `nutrition_core` with golden cases anchored to ICMR-NIN's own published
  figures: the reference man (65 kg, sedentary/moderate/heavy) must compute to 2110/2710/3470
  kcal and the reference woman (55 kg) to 1660/2130/2720 kcal, protein to 54.0 g and 45.7 g.
  These six energy values are the strongest available check that the formula is right.
- Property tests on the compensation engine: adjusted targets never exceed the upper limit,
  never fall below the EAR floor, protein never carries forward, debt always expires after 2
  days, and the ledger recomputed from scratch equals the incrementally built one. Explicit
  negative tests too: no surplus warning is ever raised on dietary magnesium, or on thiamine,
  riboflavin, biotin, B12 or potassium, since none of those has a food-based ceiling.
- Planner constraint tests: generated plans contain zero allergen and zero condition-hard-block
  violations across a matrix of representative profiles, and weekly nutrient gaps stay under
  threshold. Drug-interaction cases get their own tests — no food inside a levothyroxine
  window, no potassium push for a user on an ACE inhibitor, no vitamin K swing for a user on
  warfarin, and no non-veg (egg included) on an observance day.
- Cycle regression tests that lock in the counter-intuitive rules: logging a period must leave
  the iron target unchanged, and cycle phase must never alter the calorie target. These are
  exactly the behaviours a well-meaning future change would "fix" in the wrong direction, so
  they get tests that state why.
- API integration tests against a test database; Vitest + React Testing Library for the
  logging flow; one Playwright smoke test covering onboarding → log → dashboard.

**Manual end-to-end** (the real proof)
1. Start Postgres, run migrations, run the ETL seed, start backend and frontend.
2. Sign in with Google; complete onboarding as a user with, say, prediabetes and high cholesterol.
3. Confirm the generated targets reflect both conditions (absolute fiber floor applied,
   saturated fat capped at 7% of calories), that a sedentary profile gets the sedentary
   B-vitamin column rather than the moderate one, and that a hypertension + hypotension
   combination triggers the conflict flag instead of an averaged sodium number.
4. Log a day with a deliberate calcium shortfall; confirm tomorrow's calcium target rises by
   the capped amount and that **protein does not**.
5. Log a very high-sodium day (pickle + appalam); confirm the next days' sodium targets drop.
6. Generate a 7-day plan; swap a dish; lock a meal; regenerate a day.
7. Log a lunch that differs from the plan; confirm only the rest of that day re-plans.
7b. Add a morning levothyroxine dose and confirm the plan pushes breakfast coffee past the
    60-minute window; add an ACE inhibitor to a hypertensive profile and confirm the
    potassium-loading suggestions disappear in favour of a clinician flag.
8. Enter two weigh-ins showing drift from goal; confirm the calorie target moves by a bounded step.
9. Open the weekly report; confirm it shows hits, misses, uncompensated gaps, and next-week
   food suggestions.
10. Invite a second Google account to the household; confirm a custom dish created by one
    member appears for the other, that progress is visible, and that health conditions and
    weight stay hidden until explicitly shared.
11. Set a "vegetarian on Tuesdays and Fridays" rule and a Purattasi date range; regenerate the
    week and confirm no non-veg appears on those days, and that the following days compensate
    any B12 or iron shortfall the restriction caused.
12. Log a restaurant pizza; confirm it is found via the USDA data, marked estimated, and shown
    separately from measured intake in the weekly report.
13. Open the app on a desktop browser and confirm the dashboard and report use the wider
    viewport rather than rendering as a stretched phone layout.
14. Enable cycle tracking on a woman's profile, log a period, and confirm the iron target
    **does not move**, that coffee/tea timing and vitamin-C pairing coaching appears, and that
    answering yes to the heavy-bleeding screening questions produces a clinician referral
    rather than a raised iron goal.
15. Set a profile to postmenopausal and confirm the iron target drops to the IOM value with its
    source note, instead of silently keeping 29 mg.
16. Set breakfast to 8:00 in the profile, grant notification permission, and confirm a push
    arrives for that slot when nothing has been logged — and that it stops once the meal is
    logged or the slot's reminder is switched off.

---

## Safety

The app handles medical conditions, so it must state plainly that it is **not medical advice**
and does not replace a clinician or a registered dietitian. Condition-based adjustments follow
published guidelines but are general, not personalized medical treatment. The app never
recommends changing medication, flags conflicting condition rules for clinician review rather
than resolving them silently, and warns rather than rebalances on acute overdose-level intakes.

Three specific commitments that came directly out of the research:

- **Evidence is labelled, not laundered.** Anything resting on traditional use alone — Siddha
  and Ayurvedic formulations, jaggery and iron-kadai iron claims, "avoid cold foods" — is
  presented as traditional practice, never as established nutrition. Interventions with real
  trial support say so, and say how strong it is.
- **Nutrition is never positioned as a substitute for treatment.** NSAIDs substantially
  outperform every dietary intervention for period pain, and heavy bleeding needs a clinician.
  The app says this plainly instead of implying food is enough.
- **Doses that worked in trials are not implied to work at supermarket strength.** Vitamin D
  reduced period pain at prescription-level doses only, so it is framed as general adequacy.
  Suggested B6 stays well below the strictest applicable upper limit, since Europe's is 12 mg a
  day against ICMR's 100 and the failure mode is peripheral neuropathy.
