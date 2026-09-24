import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { HouseholdScreen } from './HouseholdScreen'

const SUDEV = {
  id: 'u-sudev',
  email: 'sudev@example.com',
  name: 'Sudev',
  timezone: 'Asia/Kolkata',
}

/** Deliberately NOT first in the member list — see the regression tests below. */
const HOUSEHOLD = {
  id: 'h1',
  name: 'Sudev Home',
  members: [
    {
      user_id: 'u-amma',
      name: 'Amma',
      email: 'amma@example.com',
      share_progress: true,
      share_health: true,
    },
    {
      user_id: 'u-sudev',
      name: 'Sudev',
      email: 'sudev@example.com',
      share_progress: false,
      share_health: false,
    },
  ],
}

beforeEach(() => {
  server.use(http.get(apiUrl('/auth/me'), () => HttpResponse.json(SUDEV)))
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <HouseholdScreen />
    </QueryClientProvider>,
  )
}

function withoutHousehold() {
  server.use(http.get(apiUrl('/households/me'), () => new HttpResponse('none', { status: 404 })))
}

function withHousehold() {
  server.use(http.get(apiUrl('/households/me'), () => HttpResponse.json(HOUSEHOLD)))
}

test('a user with no household is told solo tracking is fine', async () => {
  withoutHousehold()
  renderScreen()

  expect(await screen.findByText(/tracking on your own/i)).toBeInTheDocument()
})

test('a user with no household can either create or join one', async () => {
  withoutHousehold()
  renderScreen()

  expect(await screen.findByRole('button', { name: /create household/i })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /join household/i })).toBeInTheDocument()
  expect(await screen.findByPlaceholderText(/invite token/i)).toBeInTheDocument()
})

test('lists members and their sharing state', async () => {
  withHousehold()
  renderScreen()

  expect(await screen.findByText('Sudev Home')).toBeInTheDocument()
  expect(await screen.findByText('amma@example.com')).toBeInTheDocument()
})

test('a member can leave the household', async () => {
  withHousehold()
  renderScreen()

  expect(await screen.findByRole('button', { name: /leave household/i })).toBeInTheDocument()
})

/*
 * Regression: the screen used to read `household.members[0]`, assuming you are
 * first in the list. You are not — order comes from the membership query. A
 * second member therefore saw, and toggled, the FIRST member's sharing settings.
 * Amma shares both; Sudev shares neither.
 */
test('shows your own progress-sharing setting, not the first member’s', async () => {
  withHousehold()
  renderScreen()

  expect(await screen.findByRole('checkbox', { name: /share my daily progress/i })).not.toBeChecked()
})

test('shows your own health-sharing setting, not the first member’s', async () => {
  withHousehold()
  renderScreen()

  expect(await screen.findByRole('checkbox', { name: /share my health details/i })).not.toBeChecked()
})

// Cycle data falls under the same switch, so the switch must say so: whichever
// endpoint first honours it will share cycle data under this label.
test('names cycle data among the health details the switch shares', async () => {
  withHousehold()
  renderScreen()

  expect(
    await screen.findByRole('checkbox', {
      name: 'Share my health details (conditions, weight, cycle)',
    }),
  ).toBeInTheDocument()
})
