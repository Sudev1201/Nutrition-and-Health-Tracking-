import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, api } from './api'

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
