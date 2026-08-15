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

test('offers to create a household when the user has none', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async () => new Response('none', { status: 404 })),
  )

  renderScreen()

  expect(await screen.findByRole('button', { name: /create household/i })).toBeDefined()
})

test('lists members and their sharing state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
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
          }),
          { status: 200 },
        ),
    ),
  )

  renderScreen()

  expect(await screen.findByText('Sudev Home')).toBeDefined()
  expect(await screen.findByText('sudev@example.com')).toBeDefined()
})
