const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property,
  // which `erasableSyntaxOnly` in tsconfig disallows.
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }
  if (response.status === 204) {
    return null as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  // Takes an optional body: `DELETE /diary/skips` identifies the skip by date
  // and slot rather than by an id, because a skip has no id worth exposing.
  del: <T>(path: string, body?: unknown) => request<T>('DELETE', path, body),
}

/**
 * The sentence FastAPI sent with a failed request, or `fallback` when there is none.
 *
 * `ApiError.message` is the raw response body. A route that raises
 * `HTTPException` answers `{"detail": "..."}`, and those sentences are written
 * for the user to read. A request-validation 422 carries a list in `detail`
 * instead, a proxy's error page is not JSON at all, and neither is written for
 * anyone, so both get the fallback.
 */
export function errorDetail(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  let body: unknown
  try {
    body = JSON.parse(error.message)
  } catch {
    return fallback
  }
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string' && detail.trim() !== '') return detail
  }
  return fallback
}
