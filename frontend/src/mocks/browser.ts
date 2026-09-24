import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

// In dev the worker answers only the opt-in demo-auth handlers; every other request
// passes through to the real API.
export const worker = setupWorker(...handlers)
