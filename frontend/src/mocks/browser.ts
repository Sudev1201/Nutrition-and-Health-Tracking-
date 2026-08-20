import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/**
 * The dev-time mock worker. It only answers the endpoints plans 3-8 have yet to
 * build; everything else is passed straight through to the real FastAPI server,
 * so signing in, households and food search exercise live code while the
 * dashboard and planner serve themselves.
 */
export const worker = setupWorker(...handlers)
