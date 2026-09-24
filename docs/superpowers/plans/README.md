# Implementation Plans — South Indian Nutrient Tracker

The design spec at `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`
covers nine subsystems. It is delivered as a sequence of plans rather than one document, so
each plan produces working, testable software on its own and can be reviewed before the next
begins.

| # | Plan | Deliverable | Status |
|---|---|---|---|
| 1 | Foundation, auth & households | Sign in with Google, optional household, protected shell | **Complete** — `2026-08-15-foundation-auth-households.md` |
| 2 | Food & reference data | IFCT ingredients (unit-normalised), authored South Indian recipes, INDB reference dishes, USDA gap-fill, ICMR RDA/TUL tables — all source-tagged and searchable | **Written** — `2026-08-16-food-reference-data.md` |
| 2.5 | UI foundation & prototype | Design tokens, component library, responsive shell (phone tabs / desktop sidebar), PWA, and every screen — live where endpoints exist, MSW-backed where they do not | **Complete** — `2026-08-17-ui-foundation.md` |
| 3 | `nutrition_core` | Energy, targets, condition rules, drug interactions, compensation ledger — pure logic, heaviest test coverage | **Complete** — `2026-08-17-tracking-loop.md` |
| 4 | Onboarding & daily targets | Profile questionnaire, meal times, observance rules, usual-intake wizard, first computed targets | **Complete** — `2026-08-17-tracking-loop.md`. Includes the usual-intake wizard and the computed baseline |
| 5 | Logging & daily dashboard | Per-slot meal logging, editable dish ingredients, restaurant/estimated entries, today's view | **Complete except one dropped item** — `2026-08-17-tracking-loop.md`, closed out by `2026-08-20-plan-5-closeout.md`. Logging in household measures, estimated entries, the daily view, per-day meal skipping and a configurable meal count are live. Editable dish ingredients was dropped from scope |
| 6 | Meal planner | 7-day generation, swap/lock/regenerate, intra-day re-plan, household cooking view | **Complete** — `2026-09-02-meal-planner.md`. Generated on demand rather than on a Saturday schedule; one dish per slot (the paired snack beverage needs a beverage tag the seed data lacks) |
| 7 | Weight & cycle | Weigh-ins, trend smoothing, calorie recalibration, cycle logging and coaching | **Complete** — `2026-09-24-weight-and-cycle.md`. Recalibration is evaluated when a weigh-in is posted rather than on a schedule; postmenopausal status and the IOM iron fallback live on the profile |
| 8 | Weekly report & reminders | Nutrient report, uncompensated gaps, next-week suggestions, web push at meal times | Not started |
| 9 | LLM polish & deploy | BYO-key polish adapter, hosting, domain, seed migration | Not started |

Order matters: plans 2 and 3 are independent of each other but both gate plan 4, and everything
downstream depends on plan 3's engine.

Plan 2.5 sits out of the original sequence. The UI was going to be built piecemeal across plans
4–8; building it as one subsystem first means those plans wire existing screens to real
endpoints rather than designing a dashboard and a planner from scratch each time. Its MSW
handlers and per-feature `types.ts` files are the **proposed HTTP contract** each of those plans
implements — see the "What plans 3–8 inherit" section of `2026-08-17-ui-foundation.md`.

Plan 5's remaining follow-ups, and the debt carried over from plans 2.5 and 3–4, were closed in
`2026-08-20-plan-5-closeout.md`. Two items were deliberately moved rather than done: editable
dish ingredients was dropped from scope, and the `drug_interaction_rules` table went to phase 2
with the rest of the prescription and meal-alteration work — the spec itself says three of its
five interactions must be re-verified against a drug reference before being encoded.

Plan 6's decisions and the gaps it leaves are recorded at the top and bottom of
`2026-09-02-meal-planner.md`.

Plan 7's decisions and the gaps it leaves are recorded at the top and bottom of
`2026-09-24-weight-and-cycle.md`.

Each plan is written only when its predecessor is complete, so it can account for what actually
got built rather than what was predicted.
