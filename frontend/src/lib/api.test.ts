import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, api, errorDetail } from './api'

afterEach(() => vi.unstubAllGlobals())

test('sends credentials so the session cookie travels', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200 }),
  )
  vi.stubGlobal('fetch', fetchMock)

  await api.get('/auth/me')

  const [, init] = fetchMock.mock.calls[0]
  expect(init.credentials).toBe('include')
})

test('throws an ApiError carrying the status code', async () => {
  // A fresh Response per call: a body can only be read once.
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async () => new Response('nope', { status: 401 })),
  )

  await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
  await expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 })
})

test('returns null for an empty 204 response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

  await expect(api.post('/auth/logout', {})).resolves.toBeNull()
})

// A route's HTTPException carries a sentence written for the user; anything else
// is not, and the screen says something of its own instead.
const SENTENCE = JSON.stringify({ detail: 'Anthropic refused this key' })
const VALIDATION_LIST = JSON.stringify({
  detail: [{ loc: ['body', 'model'], msg: 'Field required', type: 'missing' }],
})

test.each([
  ['a route’s sentence', SENTENCE, 'Anthropic refused this key'],
  ['a validation list', VALIDATION_LIST, 'fallback'],
  ['an empty sentence', '{"detail": "  "}', 'fallback'],
  ['a body with no detail', '{"error": "nope"}', 'fallback'],
  ['a body that is not JSON', '<html>Bad gateway</html>', 'fallback'],
])('errorDetail reads %s', (_case, body, expected) => {
  expect(errorDetail(new ApiError(422, body), 'fallback')).toBe(expected)
})

test('errorDetail falls back for an error that did not come from the API', () => {
  expect(errorDetail(new TypeError('Failed to fetch'), 'fallback')).toBe('fallback')
})
