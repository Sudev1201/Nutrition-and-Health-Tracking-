# UI Foundation & Clickable Prototype — Design

## Context

Plans 1 and 2 delivered `auth`, `households` and `GET /foods/search`. The frontend was a
scaffold: a sign-in screen, a placeholder home screen and a household screen, all written with
ad-hoc Tailwind utilities and a desktop-shaped top nav. There was no token layer, no component
library and no mobile layout, while twenty-plus screens were still to come.

This design covers the UI as a subsystem: a token-driven design system, a responsive shell that
is a phone app on small screens and a dashboard on wide ones, PWA installability, and every
major screen of the product.

Screens whose endpoints exist run on live data. Screens whose endpoints do not exist yet run
against MSW handlers, and **those handlers are the proposed HTTP contract for plans 3–8**.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Platform | Responsive web + PWA | Matches the spec's existing decision; one codebase; the service worker is what phase-1 browser push needs |
| Phone navigation | Five tabs — Today, Log, Plan, Report, More | Logging happens five times a day, so it earns a permanent tab |
| Wide navigation | Left sidebar with the More items expanded inline | A 1440px window has room for all nine destinations; importing the phone's constraint would be gratuitous |
| Visual tone | Neutral greys, one teal accent, semantic status colour, tabular figures, flat cards | Sober enough to sit beside lab values and medication timings |
| Mock transport | MSW with passthrough | Components and hooks are written exactly as they will ship; when an endpoint lands, a handler is deleted and nothing else changes |

## Design system

Tokens live in `@theme` in `frontend/src/index.css` (Tailwind v4 is CSS-first). Dark values
redefine the same token names under `prefers-color-scheme`, so no component branches on theme.

**Status colour is the only colour that carries meaning**, and `src/lib/status.ts` owns the
mapping as one pure function. Two domain rules are encoded there rather than in any screen:

- A **null TUL never reaches `above-limit`.** ICMR deliberately set no upper limit for thiamine,
  riboflavin, biotin, B12 and potassium, and the spec forbids raising a food-based surplus
  warning for them. A regression test asserts that 340% of the B12 RDA reads as "over target".
- **Sodium is a `ceiling`, not a target.** A sodium deficit is explicitly not a thing to
  compensate, so a low-sodium day reads as fine rather than as a shortfall.

**Colour is never the only signal.** Every bar and tile carries a text label ("under target",
"past the upper limit") so the design survives colour-blindness, screenshots and print.

### Two display rules found by building it

- **Precision follows the magnitude, not the unit.** Rounding all micrograms to whole numbers
  rendered B12's 2.2 µg RDA as "2 µg" and a 7.5 µg intake as "8 µg" — over 30% error on a
  nutrient whose entire scale is single digits. `formatAmount` keeps one decimal below 10.
- **The `NutrientBar` track spans 0 → today's target, stretching to fit an overshoot.** A TUL
  2.5× the target sits off the end of that track, so the limit tick is drawn only once intake is
  actually in range of it; drawing it on every ordinary row would be noise.

## Responsive shell

`src/shell/navigation.ts` is the single source of truth for label, icon and path. `BottomTabs`
and `Sidebar` both read it, so the two layouts cannot drift as screens are added.

The switch is pure CSS, not a `useMediaQuery` branch — no layout flash on first paint, no second
render on resize. `useMediaQuery` is reserved for cases where the DOM itself must differ.

Mobile specifics: `viewport-fit=cover` plus `env(safe-area-inset-*)` so the tab bar clears the
iPhone home indicator; a 16px input font floor so iOS Safari does not zoom on focus and strand
the user mid-logging; 44px minimum touch targets.

`Sheet` is built on native `<dialog>` for a real focus trap, Esc-to-dismiss, an inert background
and top-layer stacking. jsdom 30 implements none of `<dialog>`'s methods, so `setupTests.ts`
shims it — meaning the trap and Esc handling are verified in a browser, not in unit tests.

## Mock layer

MSW with `onUnhandledRequest: 'bypass'`. Handlers exist only for endpoints that do not exist
yet, so in dev the real FastAPI serves auth, households and food search while the prototype
screens serve themselves. Mocks are dev/test only and dynamically imported, so MSW is absent
from the production bundle.

MSW's worker and the PWA worker both claim root scope, so they never run together: MSW in dev,
the PWA worker in the production build.

**Every mocked screen renders a `Demo data` banner** naming the missing endpoint. This is a
health app; a plausible-looking calcium target typed by hand must never be mistaken for one
computed from ICMR-NIN figures.

Fixtures exercise the awkward states, not a happy path: a calcium shortfall carried in from
Friday, sodium past its ceiling, protein short with no carry, B12 far over its RDA with no
limit to breach, a hypertension + hypotension conflict, a levothyroxine timing note, a skipped
optional snack and an estimated restaurant entry.

`VITE_DEMO_AUTH=true` additionally mocks the real auth endpoints so the prototype can be walked
through without Postgres and a Google OAuth client. It is off by default and must never be
enabled in a deployed build.

## Proposed endpoint contracts

Defined by the handlers in `frontend/src/mocks/handlers/` and typed in each feature's
`types.ts`. These are a **proposal to be confirmed** when each backend plan is written.

| Endpoint | Types | Lands in |
|---|---|---|
| `GET/PUT /profile` | `src/onboarding/types.ts` | Plan 4 |
| `GET /targets/today?date=` | `src/today/types.ts` | Plans 3–4 |
| `GET /diary?date=`, `POST/DELETE /diary/entries` | `src/log/types.ts` | Plan 5 |
| `GET /plan/week?start=`, swap / lock / regenerate, `GET /plan/cooking` | `src/plan/types.ts` | Plan 6; plan 9 adds each item's `description` and `cooking_note` |
| `GET /reports/week?start=` | `src/report/types.ts` | Plan 8 (built; contract amended) |
| `GET/POST /weight`, `DELETE /weight/{date}` | `src/weight/types.ts` | Plan 7 (built; contract amended) |
| `GET/PATCH/DELETE /cycle`, `PUT/DELETE /cycle/days/{date}`, `POST /cycle/screening` | `src/cycle/types.ts` | Plan 7 (built; contract amended) |
| `GET/PATCH /settings/reminders`, `GET /push/public-key`, `POST/DELETE /push/subscriptions` | `src/settings/types.ts` | Plan 8 (built; contract amended) |
| `GET/PUT/DELETE /settings/llm` | `src/settings/types.ts` | Plan 9 (built; new) |
| `POST /plan/week/polish`, answering the week and an `X-Dishes-Described` header | `src/plan/types.ts` | Plan 9 (built; new) |

Two shape notes worth carrying into the backend plans:

- `targets/today` returns both the published `rda` and the ledger-adjusted `target_effective`,
  plus `carried_in` and `carried_from`. The UI shows the carry as its own bar segment and names
  the day it came from — without that the compensation ledger is invisible to the user.
- `diary` slots carry a three-way `state` of `logged | empty | skipped`. Skipped is not the same
  as empty: the mid-morning snack is optional by design and must not read as a missed meal.

## Domain rules locked in by tests

These are behaviours a well-meaning future change would "fix" in the wrong direction, so each
has a test that states why:

- Logging a period **does not raise the iron target**. ICMR's 29 mg/day for women already
  averages menstrual loss across the cycle; the giveaway is that the pregnancy RDA (27 mg) is
  lower. The cycle screen says so in as many words.
- Cycle phase **does not change the calorie target**. The real luteal increase is ~32 kcal/day
  once anovulatory cycles are accounted for, well inside normal variation.
- Heavy bleeding produces a **clinician referral, never a nutrient change**.
- A nutrient with no TUL **never raises a surplus alarm**, however far over the RDA.
- Protein **never carries forward**, and the weekly report says why.
- Conflicting conditions are **flagged, never averaged**, both at onboarding and on Today.
- A medication without a dose time **cannot be saved** — the planner checks breakfast against it
  for the 60-minute levothyroxine window.
- Onboarding **never asks for height**: the ICMR energy equations are weight-based and the spec
  found published reference heights unverifiable.

## Bug fixed in passing

`HouseholdScreen` read `household.members[0]` as the current user. Member order comes from the
membership query and is not stable, so a second member saw and toggled the *first* member's
sharing settings — including whether their health data was shared. Now matched by `user_id`
against the session, with a regression test.

## Performance

Recharts is by far the heaviest dependency, and only Report and Weight draw charts. Those two
routes are `React.lazy`-split, taking the entry chunk from 708 KB to 323 KB (100 KB gzipped) so
a cold start on a phone does not pay for a charting library most sessions never open.

## Not in scope

The Playwright smoke test the parent spec calls for (onboarding → log → dashboard). Against
mocks it would only assert that MSW returns what MSW was told to return. It belongs in plan 5,
once those flows are real.
