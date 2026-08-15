# Implementation Plans — South Indian Nutrient Tracker

The design spec at `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`
covers nine subsystems. It is delivered as a sequence of plans rather than one document, so
each plan produces working, testable software on its own and can be reviewed before the next
begins.

| # | Plan | Deliverable | Status |
|---|---|---|---|
| 1 | Foundation, auth & households | Sign in with Google, create a household, invite a member, land on a protected shell | **Written** — `2026-08-15-foundation-auth-households.md` |
| 2 | Food & reference data | INDB recipes, IFCT ingredients, USDA gap-fillers, ICMR RDA/EAR/TUL tables, all source-tagged and queryable | Not started |
| 3 | `nutrition_core` | Energy, targets, condition rules, drug interactions, compensation ledger — pure logic, heaviest test coverage | Not started |
| 4 | Onboarding & daily targets | Profile questionnaire, meal times, observance rules, usual-intake wizard, first computed targets | Not started |
| 5 | Logging & daily dashboard | Per-slot meal logging, editable dish ingredients, restaurant/estimated entries, today's view | Not started |
| 6 | Meal planner | 7-day generation, swap/lock/regenerate, intra-day re-plan, household cooking view | Not started |
| 7 | Weight & cycle | Weigh-ins, trend smoothing, calorie recalibration, cycle logging and coaching | Not started |
| 8 | Weekly report & reminders | Nutrient report, uncompensated gaps, next-week suggestions, web push at meal times | Not started |
| 9 | LLM polish & deploy | BYO-key polish adapter, hosting, domain, seed migration | Not started |

Order matters: plans 2 and 3 are independent of each other but both gate plan 4, and everything
downstream depends on plan 3's engine.

Each plan is written only when its predecessor is complete, so it can account for what actually
got built rather than what was predicted.
