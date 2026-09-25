# Nutrient Tracker — frontend

React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, React Router 7. A responsive web app
that is a phone app below `md` and a dashboard from `md` up, installable as a PWA.

Design notes: `docs/superpowers/specs/2026-08-17-ui-foundation-design.md`.

## Running it

```bash
npm install
npm run dev
```

Every screen talks to the real FastAPI backend on
`VITE_API_BASE` (default `http://localhost:8000`), which needs Postgres running:

```bash
docker compose up -d db          # from the repo root
cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
```

The frontend's settings are build-time `VITE_*` variables, all listed in `.env.example`.
Copy it to `.env.local`, which is git-ignored, and fill in `VITE_GOOGLE_CLIENT_ID` and
`VITE_API_BASE`. Every `VITE_*` value is baked into the bundle, so none of them is a secret.

### Without a Google OAuth client

Every screen needs the backend and Postgres (see above). Demo auth gets you past the sign-in
screen without Google:

```bash
VITE_DEMO_AUTH=true npm run dev
```

This fakes `/auth/*` in the browser only. The backend still has no session, so every other
request answers 401: you get the shell and each screen's error state, not your data. The
end-to-end walk gets a real session a different way, through `backend/scripts/e2e_session.py`
(see "End to end"). **Never enable demo auth in a deployed build.** It hands a session to
anyone who asks.

## Which screens are real

**Live against the real backend:** every screen. That covers sign-in, household (with the
week's shared progress), food search, the onboarding questionnaire and profile, Today, meal
logging, the meal plan, weight, cycle tracking, the weekly report, reminders and AI descriptions.

**Push reminders need a production build.** The browser subscribes only under the production
service worker (`npm run build && npx vite preview --port 5173`, the origin the backend's CORS
allows by default), and the backend sends with VAPID keys set and either `SCHEDULER_ENABLED=true`
or `uv run python -m scripts.send_reminders` run from cron. See `backend/.env.example`.

**AI descriptions need a server keyring and the user's own key.** With
`LLM_KEY_ENCRYPTION_KEYS` unset, which is the default, the AI descriptions screen says the
feature is not set up on this server and the Plan screen offers nothing. With it set (see
`backend/.env.example`), a user saves their own Anthropic API key, and "Add descriptions" on
the Plan screen asks Claude for a one-line description and a cooking tip for each dish.
Only dish and ingredient names are sent, and no dish, portion or number changes. When a
polish stores no new text (every dish already had some, Claude declined, or it wrote
nothing the server's check kept), the Plan screen says "Claude added no new descriptions
this time." No test and no end-to-end walk ever reaches Anthropic.

Mocks are on in dev and off in a production build. No fixture handlers are left, so the mock
worker serves only opt-in demo auth. Override with `VITE_USE_MOCKS=false` (no worker at all) or
`true`. MSW is dynamically imported, so it is not in the production bundle.

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

A production build refuses to run without `VITE_API_BASE`, because the bundle would
otherwise call `http://localhost:8000`. Set it in `.env.local`. `VITE_USE_MOCKS=true` also
lets the build through, for a local build that is never deployed.

### End to end

```bash
npm run test:e2e   # Playwright: onboarding -> log -> dashboard, then the plan, weight, cycle, report, reminders and AI descriptions
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

## Deploying

The web app is built for Cloudflare Pages: `npm run build` with `VITE_API_BASE` and
`VITE_GOOGLE_CLIENT_ID` set, publishing `dist/`. `public/_headers` serves the service
worker's files, the manifest and the app shell (`/` and `/index.html`) `no-cache`, and the
content-hashed files (`/assets/*` and `/workbox-*.js`) as immutable. `public/_redirects`
deliberately holds no rule. Pages itself answers every path that is not a file with
`index.html`, as long as the build has no top-level `404.html`. Never add a `/*` rule there:
Pages applies `_redirects` before it looks for a file, so a catch-all would answer `/sw.js`
and every script under `/assets/` with HTML. Never add a `404.html` to `public/` either.

The app must be served at the root of its own host, under the same registrable domain as the
API, or the session cookie is never sent.

`DEPLOY.md` at the repository root is the runbook. Nothing has been deployed.
