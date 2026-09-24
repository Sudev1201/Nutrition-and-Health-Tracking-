# Nutrient Tracker — frontend

React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, React Router 7. A responsive web app
that is a phone app below `md` and a dashboard from `md` up, installable as a PWA.

Design notes: `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`.

## Running it

```bash
npm install
npm run dev
```

Every screen but Report and Reminders talks to the real FastAPI backend on
`VITE_API_BASE` (default `http://localhost:8000`), which needs Postgres running:

```bash
docker compose up -d db          # from the repo root
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
```

### Without a backend

Report and Reminders are not wired to a backend yet (see below), and the ones that are need
Postgres and a Google OAuth client. To walk the whole app without either:

```bash
VITE_DEMO_AUTH=true npm run dev
```

This mocks `/auth/*` so you land straight in the app. **Never enable it in a deployed build** —
it hands a session to anyone who asks.

## Which screens are real

**Live against the real backend:** sign-in, household, food search, the onboarding
questionnaire and profile, Today (real ICMR-NIN targets and the compensation ledger),
meal logging, the meal plan (generation, swap, lock, regenerate, and the household
cooking view), weight (weigh-ins, the trend and calorie recalibration) and cycle
tracking.

**Still on MSW fixtures:** Report and Reminders. Each carries a **Demo data** banner
naming the endpoint it is waiting for. Those handlers and the `types.ts` in each
feature folder are the proposed contract for the remaining backend plans.

Mocks are on in dev and off in a production build. Override with `VITE_USE_MOCKS=false` (dev
against a fully real backend) or `true` (a self-contained demo build). MSW is dynamically
imported, so it is not in the production bundle.

MSW's service worker and the PWA service worker both claim the root scope, so they never run
together: mocks own dev, the PWA worker owns the production build.

## Layout

```
src/
  lib/        pure helpers — status.ts, format.ts, cx.ts, api.ts
  ui/         the component library and the status→colour/label mapping
  shell/      AppShell, BottomTabs, Sidebar, TopBar, navigation.ts
  mocks/      MSW handlers and fixtures
  <feature>/  one folder per screen area, each with its own types.ts and hooks
```

`src/shell/navigation.ts` is the single source of truth for navigation — the phone tab bar and
the desktop sidebar both read it, so they cannot drift apart.

`src/lib/status.ts` is the single source of truth for what a nutrient reading means. Nothing
else decides what colour a number is.

## Checks

```bash
npm test           # unit and component tests, MSW-backed
npx tsc -b         # typecheck every project reference
npm run build      # tsc -b, then the production bundle and service worker
npm run lint       # oxlint
```

`npm run build` is the authoritative typecheck — `npx tsc --noEmit` alone does not build the
project references and will miss errors.

### End to end

```bash
npm run test:e2e   # Playwright: onboarding -> log -> dashboard, then the plan, weight and cycle
```

Deliberately against the **real** backend and a real Postgres, never against MSW — run against
mocks it would assert only that the mocks return what they were told, which is why this layer
was deferred rather than written earlier.

Auth is real too. `backend/scripts/e2e_session.py` signs a genuine session token with the app's
own code and `e2e/globalSetup.ts` puts it in the browser's cookie jar, so the walk goes through
the same `get_current_user` path a signed-in person does. Demo auth is explicitly *off*: it
fakes `/auth/me` in the browser while the backend still has no session, which would leave every
real endpoint answering 401.

It needs a database and an API, which it does not start for you:

```bash
docker compose up -d db
cd backend && uv run alembic upgrade head
cd backend && uv run python -m scripts.e2e_seed      # offline: nutrients, ICMR rows, 5 foods
cd backend && uv run uvicorn app.main:app --port 8000
```

`e2e_seed` runs only the loaders that need no downloads, so the walk works on a database that
has never run the full ETL. Each spec owns a different meal slot, because `globalSetup` resets
the test user once per run rather than once per test.

If a local `http_proxy` is set, note that a `no_proxy` list covering `127.0.0.1` but not
`localhost` will send Playwright's readiness check to the proxy and surface as
"timed out waiting for webServer". The config adds `localhost` to `no_proxy` and passes
`--no-proxy-server` to Chromium for that reason.

### Verified manually, not by tests

- `Sheet`'s focus trap. It uses a native `<dialog>`, and jsdom 30 implements none of that
  element's methods, so `src/setupTests.ts` shims it. Esc-to-dismiss is now covered by the
  Playwright run against a real browser; the focus trap still is not.
- The responsive breakpoint itself. jsdom does not evaluate CSS, so both layouts are present in
  the DOM during tests; check the real thing in a browser at 390px and 1440px.
