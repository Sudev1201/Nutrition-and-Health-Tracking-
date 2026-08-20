import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/**
 * The Node-side mock server used by Vitest. Tests add per-test handlers with
 * `server.use(...)`; `src/setupTests.ts` resets them between tests so one test's
 * stubbing cannot leak into the next.
 */
export const server = setupServer(...handlers)
