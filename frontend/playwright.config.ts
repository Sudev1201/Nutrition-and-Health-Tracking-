import { defineConfig, devices } from '@playwright/test'

const FRONTEND = 'http://localhost:5173'

/*
 * Everything in this run is local, so the proxy must be out of the way.
 *
 * A corporate `http_proxy` with a `no_proxy` list that covers 127.0.0.1 but not
 * `localhost` sends Node's web-server readiness check to the proxy, which answers
 * 503 -- and Playwright reports that as "timed out waiting for webServer", which
 * points at the wrong thing entirely. Chromium gets `--no-proxy-server` for the
 * same reason.
 */
const NO_PROXY = ['localhost', '127.0.0.1', '::1', process.env.no_proxy ?? '']
  .filter(Boolean)
  .join(',')

process.env.no_proxy = NO_PROXY
process.env.NO_PROXY = NO_PROXY

/**
 * The end-to-end walk: onboarding -> log -> dashboard.
 *
 * Deliberately against the REAL backend and a real Postgres, not against MSW.
 * Run against mocks it would assert only that MSW returns what MSW was told,
 * which is why this layer was deferred rather than written earlier. Auth is real
 * too: `backend/scripts/e2e_session.py` signs a genuine session token with the
 * app's own code and `globalSetup` puts it in the browser's cookie jar, so the
 * run exercises the same `get_current_user` path a signed-in person does.
 *
 * `VITE_USE_MOCKS=false` is the load-bearing part of the web server config. In
 * dev, mocks default to on, and MSW's service worker would intercept the very
 * requests this test exists to exercise.
 *
 * Prerequisites, which the run does not create for you:
 *   docker compose up -d db
 *   cd backend && uv run alembic upgrade head
 *   cd backend && uv run python -m scripts.e2e_seed
 *   cd backend && uv run uvicorn app.main:app --port 8000
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/globalSetup.ts',
  // One worker: every spec drives the same backend user, so parallel runs would
  // reset each other's profile mid-walk.
  workers: 1,
  fullyParallel: false,
  // A flake here means a real ordering or timing bug in the app, so a retry
  // locally would only hide it. CI retries once to absorb genuine cold starts.
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: FRONTEND,
    storageState: './e2e/.auth/state.json',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--no-proxy-server'] },
    // The browser's date must be the e2e user's. The weight walk compares a weigh-in
    // the browser dates (`todayIso()`) with the one onboarding recorded, which the
    // server dates in the user's zone -- Asia/Kolkata, set in
    // backend/scripts/e2e_session.py. On a UTC CI runner they differ from 18:30 UTC.
    timezoneId: 'Asia/Kolkata',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: FRONTEND,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // Mocks off, so the walk reaches FastAPI. Demo auth off too -- it fakes
      // /auth/me in the browser while the backend still has no session, which
      // would leave every real endpoint answering 401.
      VITE_USE_MOCKS: 'false',
      VITE_DEMO_AUTH: 'false',
      no_proxy: NO_PROXY,
      NO_PROXY: NO_PROXY,
    },
  },
})
