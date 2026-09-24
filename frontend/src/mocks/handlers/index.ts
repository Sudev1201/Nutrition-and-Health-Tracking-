import type { RequestHandler } from 'msw'
import { demoAuthHandlers } from './demoAuth'

/**
 * Handlers for endpoints the backend has NOT built yet. There are none left.
 *
 * Every endpoint the app calls exists in FastAPI now, the weekly report and the
 * reminders last, in plan 8. So in dev every request falls through to the real
 * server (`onUnhandledRequest: 'bypass'`), and in Vitest each test stubs what it
 * calls with `server.use(...)`.
 *
 * Demo auth is all that remains. It is opt-in, so the default set never shadows
 * a real endpoint.
 */
export const handlers: RequestHandler[] = [
  ...(import.meta.env.VITE_DEMO_AUTH === 'true' ? demoAuthHandlers : []),
]
