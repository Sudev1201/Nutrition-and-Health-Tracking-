import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
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
