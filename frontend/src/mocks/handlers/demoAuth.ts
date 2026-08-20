import { http, HttpResponse } from 'msw'
import type { RequestHandler } from 'msw'
import { apiUrl } from '../apiUrl'

const DEMO_USER = {
  id: 'demo-user',
  email: 'demo@example.com',
  name: 'Demo User',
  timezone: 'Asia/Kolkata',
}

/**
 * Auth is REAL — it is the one flow plan 1 finished — so these handlers are off
 * unless `VITE_DEMO_AUTH=true` is set explicitly.
 *
 * They exist so the clickable prototype can be walked through without standing up
 * Postgres and a Google OAuth client, which is the difference between a reviewer
 * seeing the UI in thirty seconds and not seeing it at all. Never enable this in
 * a deployed build: it would hand a session to anyone who asked.
 */
export const demoAuthHandlers: RequestHandler[] = [
  http.get(apiUrl('/auth/me'), () => HttpResponse.json(DEMO_USER)),
  http.post(apiUrl('/auth/google'), () => HttpResponse.json(DEMO_USER)),
  http.post(apiUrl('/auth/logout'), () => new HttpResponse(null, { status: 204 })),
  http.get(apiUrl('/households/me'), () => new HttpResponse('none', { status: 404 })),
]
