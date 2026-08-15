import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { HouseholdScreen } from './HouseholdScreen'

afterEach(() => vi.unstubAllGlobals())

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <HouseholdScreen />
    </QueryClientProvider>,
  )
}

function stubFetch(response: () => Response) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => response()))
}

const HOUSEHOLD = {
  id: 'h1',
  name: 'Sudev Home',
  members: [
    {
      user_id: 'u1',
      name: 'Sudev',
      email: 'sudev@example.com',
      share_progress: true,
      share_health: false,
    },
  ],
}

test('a user with no household is told solo tracking is fine', async () => {
  stubFetch(() => new Response('none', { status: 404 }))

  renderScreen()

  expect(await screen.findByText(/tracking on your own/i)).toBeDefined()
})

test('a user with no household can either create or join one', async () => {
  stubFetch(() => new Response('none', { status: 404 }))

  renderScreen()

  expect(await screen.findByRole('button', { name: /create household/i })).toBeDefined()
  expect(await screen.findByRole('button', { name: /join household/i })).toBeDefined()
  expect(await screen.findByPlaceholderText(/invite token/i)).toBeDefined()
})

test('lists members and their sharing state', async () => {
  stubFetch(() => new Response(JSON.stringify(HOUSEHOLD), { status: 200 }))

  renderScreen()

  expect(await screen.findByText('Sudev Home')).toBeDefined()
  expect(await screen.findByText('sudev@example.com')).toBeDefined()
})

test('a member can leave the household', async () => {
  stubFetch(() => new Response(JSON.stringify(HOUSEHOLD), { status: 200 }))

  renderScreen()

  expect(await screen.findByRole('button', { name: /leave household/i })).toBeDefined()
})
