# Nutrient Tracker — frontend

React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, React Router 7. A responsive web app
that is a phone app below `md` and a dashboard from `md` up, installable as a PWA.

Design notes: `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`.

## Running it

```bash
npm install
npm run dev
```

Auth, households and food search talk to the real FastAPI backend on
`VITE_API_BASE` (default `http://localhost:8000`), which needs Postgres running:

```bash
docker compose up -d db          # from the repo root
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
```

### Without a backend

Most screens are not wired to a backend yet (see below), and the ones that are need Postgres and
a Google OAuth client. To walk the whole app without either:

```bash
VITE_DEMO_AUTH=true npm run dev
```

This mocks `/auth/*` so you land straight in the app. **Never enable it in a deployed build** —
it hands a session to anyone who asks.

## Which screens are real

**Live against the real backend:** sign-in, household, food search, the onboarding
questionnaire, Today (real ICMR-NIN targets and the compensation ledger) and meal logging.

**Still on MSW fixtures:** Plan, Report, Weight, Cycle and Reminders. Each carries a
**Demo data** banner naming the endpoint it is waiting for. Those handlers and the
`types.ts` in each feature folder are the proposed contract for the remaining
backend plans.

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
npx vitest run     # unit and component tests, MSW-backed
npm run build      # tsc -b, then the production bundle and service worker
npm run lint       # oxlint
```

`npm run build` is the authoritative typecheck — `npx tsc --noEmit` alone does not build the
project references and will miss errors.

### Verified manually, not by tests

- `Sheet`'s focus trap and Esc-to-dismiss. It uses a native `<dialog>`, and jsdom 30 implements
  none of that element's methods, so `src/setupTests.ts` shims it.
- The responsive breakpoint itself. jsdom does not evaluate CSS, so both layouts are present in
  the DOM during tests; check the real thing in a browser at 390px and 1440px.
