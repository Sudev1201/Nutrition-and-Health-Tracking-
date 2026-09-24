import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'
import { apiUrl } from '../apiUrl'
import { REMINDERS_FIXTURE } from '../fixtures/more'
import { demoAuthHandlers } from './demoAuth'

/**
 * Handlers for endpoints the backend has NOT built yet.
 *
 * Nothing here shadows a real endpoint. Auth, households, food search, the whole
 * tracking loop — profile, targets and diary — the meal planner, weight, cycle
 * and the weekly report exist in FastAPI, so requests to them fall through to the
 * real server in dev (`onUnhandledRequest: 'bypass'`) and are stubbed per-test
 * in Vitest.
 *
 * These handlers are the proposed HTTP contract for the plans still outstanding.
 * When a plan implements one, delete its handler and its screen's
 * `DemoDataBanner`.
 */
export const handlers: RequestHandler[] = [
  // Opt-in only, so the default set never shadows a real endpoint.
  ...(import.meta.env.VITE_DEMO_AUTH === 'true' ? demoAuthHandlers : []),

  // Plan 8 — per-slot reminder scheduling. The meal *times* themselves are saved
  // with the profile and are real; toggling reminders is not wired up yet.
  http.get(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
  http.patch(apiUrl('/settings/reminders'), () => HttpResponse.json(REMINDERS_FIXTURE)),
]
