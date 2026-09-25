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

/** Sends one request. An answer that is not 2xx throws an `ApiError` holding its body. */
async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }
  return response
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await send(method, path, body)
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

/**
 * `api.post` for a route whose answer says something in a header as well as in
 * its body. Plan 9's `POST /plan/week/polish` puts how many dishes it described
 * in `X-Dishes-Described`. It sends through the same `send`, so it fails with
 * the same `ApiError`, which `errorDetail` reads as it reads any other.
 */
export async function postWithHeaders<T>(
  path: string,
  body: unknown,
): Promise<{ data: T; headers: Headers }> {
  const response = await send('POST', path, body)
  return { data: (await response.json()) as T, headers: response.headers }
}
