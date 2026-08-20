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
| 5 | Logging & daily dashboard | Per-slot meal logging, editable dish ingredients, restaurant/estimated entries, today's view | **Partly complete** — `2026-08-17-tracking-loop.md`. Logging in household measures, estimated entries and the daily view are live; editable dish ingredients are not |
| 6 | Meal planner | 7-day generation, swap/lock/regenerate, intra-day re-plan, household cooking view | Not started |
| 7 | Weight & cycle | Weigh-ins, trend smoothing, calorie recalibration, cycle logging and coaching | Not started |
| 8 | Weekly report & reminders | Nutrient report, uncompensated gaps, next-week suggestions, web push at meal times | Not started |
| 9 | LLM polish & deploy | BYO-key polish adapter, hosting, domain, seed migration | Not started |

Order matters: plans 2 and 3 are independent of each other but both gate plan 4, and everything
downstream depends on plan 3's engine.

Plan 2.5 sits out of the original sequence. The UI was going to be built piecemeal across plans
4–8; building it as one subsystem first means those plans wire existing screens to real
endpoints rather than designing a dashboard and a planner from scratch each time. Its MSW
handlers and per-feature `types.ts` files are the **proposed HTTP contract** each of those plans
implements — see the "What plans 3–8 inherit" section of `2026-08-17-ui-foundation.md`.

Each plan is written only when its predecessor is complete, so it can account for what actually
got built rather than what was predicted.
