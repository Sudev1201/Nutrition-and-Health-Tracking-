# UI Foundation & Clickable Prototype — Implementation Plan

**Goal:** Build the UI layer as a subsystem — design tokens, a component library, a responsive
shell, PWA installability, and every major screen — so plans 4–8 wire existing screens to real
endpoints instead of building UI from scratch.

**Spec:** `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`

**Depends on:** Plan 1 (auth, households) and plan 2 (`GET /foods/search`), both complete.

**Status:** Complete. 138 tests passing; `tsc -b`, `oxlint` and `vite build` clean.

## Tasks

- [x] 1. **Tokens, `src/ui/`, shared status presentation.** `@theme` tokens with dark-mode
      counterparts; `Button`, `Card`, `Badge`, `EmptyState`, `Skeleton`, form fields, `Sheet`,
      `SegmentedControl`, `SearchField`, `NutrientBar`, `StatTile`, `DemoDataBanner`.
      Pure logic in `src/lib/`: `status.ts`, `format.ts`, `cx.ts`.
- [x] 2. **Responsive shell.** `navigation.ts` as the single nav source, `BottomTabs`, `Sidebar`,
      `TopBar`, `AppShell` with nested routes, safe-area insets, `MoreScreen`.
- [x] 3. **Real screens.** Sign-in and household restyled; the `members[0]` bug fixed;
      `FoodSearchScreen` built on the live endpoint; household tests migrated from
      `vi.stubGlobal('fetch')` to MSW.
- [x] 4. **PWA.** `vite-plugin-pwa`, manifest, generated icon set replacing the Vite template
      favicon, offline app shell, `viewport-fit=cover` and theme-colour meta.
- [x] 5. **MSW scaffolding.** `browser.ts` / `server.ts`, fixtures, `DemoDataBanner`, the
      `VITE_USE_MOCKS` and `VITE_DEMO_AUTH` gates.
- [x] 6. **Today.** Macro tiles, micronutrient bars with carried-forward annotations, five meal
      slots, condition-conflict and medication-timing warnings.
- [x] 7. **Log flow.** Slot picker, live food search, portion sheet, estimated flag, payload
      builder.
- [x] 8. **Onboarding.** Eight steps with per-step validation, medications with dose times,
      observance rules, meal times, usual-intake wizard.
- [x] 9. **Plan.** Week view, day picker on phone and seven columns from `lg`, swap, lock,
      regenerate, vegetarian-day labelling with its reason.
- [x] 10. **Report.** Adherence figures, energy chart with an accessible table, nutrient table,
      uncompensated gaps, measured-vs-estimated split, next-week suggestions.
- [x] 11. **More section.** Weight trend and recalibration, cycle with its locked rules and
      evidence grading, per-slot reminders.
- [x] 12. **Docs.** This plan, the design spec, and the README table row.

## What plans 3–8 inherit

Each mocked screen has a `DemoDataBanner` naming the endpoint it waits on, and a `types.ts`
holding the proposed request/response shapes. Landing a backend endpoint is therefore:

1. Implement it to match the types in the feature's `types.ts` (or agree a change and update
   both sides).
2. Delete its handler from `frontend/src/mocks/handlers/index.ts`.
3. Delete the `DemoDataBanner` from that screen.
4. Delete its fixture if nothing else uses it.

No component or hook changes — they already call the real client through `src/lib/api.ts`.

## Follow-ups deliberately deferred

- **Playwright smoke test** (onboarding → log → dashboard). Against mocks it would assert only
  that MSW returns what MSW was told to return. Belongs in plan 5.
- **Profile summary screen.** `/profile` currently renders the onboarding questionnaire itself.
  A read-only summary with per-section editing is worth building once `GET /profile` is real.
- **Household cooking view.** The contract and fixture exist (`GET /plan/cooking`); the screen
  is not built, since it only makes sense with real multi-member plans.
- **Observance date ranges and one-off dates.** Onboarding collects recurring weekday rules; the
  other two shapes are noted in the UI as editable later, and the type supports all three.
- **Web push subscription.** The service worker is in place; subscribing is plan 8.
- **`under` and `over` status colours are close in hue.** Both are "needs attention" states and
  the text label always disambiguates, but the palette could separate them further.
