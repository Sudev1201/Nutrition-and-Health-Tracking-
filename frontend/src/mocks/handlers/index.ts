import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'
import { apiUrl } from '../apiUrl'
import { COOKING_FIXTURE, PLAN_FIXTURE } from '../fixtures/plan'
import { CYCLE_FIXTURE, REMINDERS_FIXTURE, WEIGHT_FIXTURE } from '../fixtures/more'
import { REPORT_FIXTURE } from '../fixtures/report'
import { demoAuthHandlers } from './demoAuth'

/**
 * Handlers for endpoints the backend has NOT built yet.
 *
 * Nothing here shadows a real endpoint. Auth, households, food search and now
 * the whole tracking loop — profile, targets and diary — exist in FastAPI, so
 * requests to them fall through to the real server in dev
 * (`onUnhandledRequest: 'bypass'`) and are stubbed per-test in Vitest.
 *
 * These handlers are the proposed HTTP contract for the plans still outstanding.
 * When a plan implements one, delete its handler and its screen's
 * `DemoDataBanner`.
 */
export const handlers: RequestHandler[] = [
  // Opt-in only, so the default set never shadows a real endpoint.
  ...(import.meta.env.VITE_DEMO_AUTH === 'true' ? demoAuthHandlers : []),

  // Plan 6 — the meal planner.
  http.get(apiUrl('/plan/week'), () => HttpResponse.json(PLAN_FIXTURE)),
  http.get(apiUrl('/plan/cooking'), () => HttpResponse.json(COOKING_FIXTURE)),
  http.post(apiUrl('/plan/week/regenerate'), () => HttpResponse.json(PLAN_FIXTURE)),
  http.post(apiUrl('/plan/items/:id/swap'), () => HttpResponse.json(PLAN_FIXTURE)),
  http.patch(apiUrl('/plan/items/:id'), () => HttpResponse.json(PLAN_FIXTURE)),

  // Plan 8 — the weekly report.
  http.get(apiUrl('/reports/week'), () => HttpResponse.json(REPORT_FIXTURE)),

  // Plan 7 — weight and cycle.
  http.get(apiUrl('/weight'), () => HttpResponse.json(WEIGHT_FIXTURE)),
  http.post(apiUrl('/weight'), () => HttpResponse.json(WEIGHT_FIXTURE, { status: 201 })),
  http.get(apiUrl('/cycle'), () => HttpResponse.json(CYCLE_FIXTURE)),
  http.patch(apiUrl('/cycle'), () => HttpResponse.json(CYCLE_FIXTURE)),

  // Plan 8 — per-slot reminder scheduling. The meal *times* themselves are saved
  // with the profile and are real; toggling reminders is not wired up yet.
  http.get(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
  http.patch(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
]
