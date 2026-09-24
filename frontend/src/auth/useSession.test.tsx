import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { ENDPOINT, installPush, uninstallPush } from '../mocks/pushApis'
import { server } from '../mocks/server'
import { RequireAuth } from './RequireAuth'
import { useSignIn, useSignOut } from './useSession'
import type { SessionUser } from './useSession'

/*
 * One device, two accounts: a family sharing a phone is the household case. The
 * query cache outlives a sign-out -- RequireAuth swaps in the sign-in screen at
 * the same route, with no reload -- so without clearing it the next account
 * would be shown the previous one's cycle days and weigh-ins until its own
 * requests land.
 */

const A: SessionUser = { id: 'a', email: 'a@example.com', name: 'A', timezone: 'Asia/Kolkata' }
const B: SessionUser = { id: 'b', email: 'b@example.com', name: 'B', timezone: 'Asia/Kolkata' }

let queryClient: QueryClient

function signedInAsA() {
  queryClient.setQueryData(['session'], A)
  queryClient.setQueryData(['cycle', '2026-09-24'], { days: ['A logged this'] })
  queryClient.setQueryData(['weight'], { weigh_ins: [{ date: '2026-09-24', weight_kg: 61 }] })
}

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

function cachedKeys(): unknown[] {
  return queryClient
    .getQueryCache()
    .getAll()
    .map((query) => query.queryKey)
}

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  server.use(
    http.post(apiUrl('/auth/logout'), () => new HttpResponse(null, { status: 204 })),
    http.post(apiUrl('/auth/google'), () => HttpResponse.json(B)),
  )
})

afterEach(() => uninstallPush())

test('signing out forgets the session and every other account data cached', async () => {
  signedInAsA()
  const { result } = renderHook(() => useSignOut(), { wrapper })

  await act(() => result.current.mutateAsync())

  expect(queryClient.getQueryData(['session'])).toBeNull()
  expect(queryClient.getQueryData(['cycle', '2026-09-24'])).toBeUndefined()
  expect(queryClient.getQueryData(['weight'])).toBeUndefined()
  expect(cachedKeys()).toEqual([['session']])
})

test('signing in starts from an empty cache, whatever was left behind', async () => {
  // A session that expired rather than signed out leaves the old account's data.
  signedInAsA()
  queryClient.setQueryData(['session'], null)
  const { result } = renderHook(() => useSignIn(), { wrapper })

  await act(() => result.current.mutateAsync('credential-for-b'))

  expect(queryClient.getQueryData(['session'])).toEqual(B)
  expect(queryClient.getQueryData(['cycle', '2026-09-24'])).toBeUndefined()
  expect(queryClient.getQueryData(['weight'])).toBeUndefined()
})

function SignOutButton() {
  const signOut = useSignOut()
  return <button onClick={() => signOut.mutate()}>Sign out</button>
}

test('signing out still shows the sign-in screen', async () => {
  signedInAsA()
  render(
    <RequireAuth>
      <SignOutButton />
    </RequireAuth>,
    { wrapper },
  )

  await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

  expect(await screen.findByRole('heading', { name: 'Nutrient Tracker' })).toBeInTheDocument()
  expect(queryClient.getQueryData(['weight'])).toBeUndefined()
})

/** Records the calls sign-out makes, in order, with the device's DELETE answering `status`. */
function serveSignOut(status = 204) {
  const calls: string[] = []
  server.use(
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      const { endpoint } = (await request.json()) as { endpoint: string }
      calls.push(`forget ${endpoint}`)
      return new HttpResponse(null, { status })
    }),
    http.post(apiUrl('/auth/logout'), () => {
      calls.push('logout')
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return calls
}

/** A signs out on a browser that has said something about push. */
async function signOutWithPush() {
  signedInAsA()
  queryClient.setQueryData(['push', 'device'], 'on')
  const { result } = renderHook(() => useSignOut(), { wrapper })

  await act(() => result.current.mutateAsync())
}

// The DELETE needs the session, and a shared phone must not go on reminding the
// person who just left it.
test('signing out forgets this device first, while the session still exists', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  const calls = serveSignOut()

  await signOutWithPush()

  expect(calls).toEqual([`forget ${ENDPOINT}`, 'logout'])
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(queryClient.getQueryData(['session'])).toBeNull()
  // What this browser said about push went with everything else of A's.
  expect(cachedKeys()).toEqual([['session']])
})

test('a device the server cannot forget does not keep anyone signed in', async () => {
  installPush({ permission: 'granted', subscribed: true })
  const calls = serveSignOut(500)

  await signOutWithPush()

  expect(calls).toEqual([`forget ${ENDPOINT}`, 'logout'])
  expect(queryClient.getQueryData(['session'])).toBeNull()
})

test('a browser without push simply signs out', async () => {
  const calls = serveSignOut()

  await signOutWithPush()

  expect(calls).toEqual(['logout'])
  expect(queryClient.getQueryData(['session'])).toBeNull()
})
