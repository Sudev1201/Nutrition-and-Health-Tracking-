import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { COOKING_FIXTURE, PLAN_FIXTURE } from '../mocks/fixtures/plan'
import { server } from '../mocks/server'
import { PlanScreen } from './PlanScreen'

/*
 * `/plan/week` is a real endpoint now, so it is stubbed per test. The fixture
 * stays because it carries the states worth asserting -- a Friday rule, a locked
 * meal, a rationale -- which a freshly generated plan would not reliably produce.
 * Solo by default: the cooking view only appears for a household member.
 */
beforeEach(() => {
  server.use(
    http.get(apiUrl('/plan/week'), () => HttpResponse.json(PLAN_FIXTURE)),
    http.get(apiUrl('/households/me'), () => new HttpResponse('no household', { status: 404 })),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * Every day is rendered once and hidden on a phone with a CSS class, which jsdom
 * does not evaluate — so all seven are in the DOM here. Each day is a landmark
 * region, so queries scope to the day under test.
 */
async function day(weekday: string) {
  return within(await screen.findByRole('region', { name: weekday }))
}

test('shows the week Sunday to Saturday', async () => {
  renderScreen()

  expect(await screen.findByRole('radio', { name: /sunday/i })).toBeInTheDocument()
  expect(await screen.findByRole('radio', { name: /saturday/i })).toBeInTheDocument()
})

test('shows the planned dish for each slot of a day', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText('Ven pongal')).toBeInTheDocument()
  expect(sunday.getByText('Rice with sambar')).toBeInTheDocument()
})

test('selecting a day makes it the one the phone shows', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('radio', { name: /friday/i }))

  expect(screen.getByRole('radio', { name: /friday/i })).toBeChecked()
  expect(screen.getByRole('radio', { name: /sunday/i })).not.toBeChecked()
})

/*
 * Observance is a hard constraint, not a preference, and on those days egg counts
 * as non-vegetarian alongside meat and fish. If the plan silently drops non-veg
 * without saying why, the user cannot tell the rule was applied.
 */
test('says when a day is vegetarian and which rule made it so', async () => {
  renderScreen()

  const friday = await day('Friday')
  expect(friday.getByText(/vegetarian/i)).toBeInTheDocument()
  expect(friday.getByText(/your Friday rule/i)).toBeInTheDocument()
})

test('does not mark an ordinary day as vegetarian', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.queryByText(/vegetarian/i)).not.toBeInTheDocument()
})

// The planner is not a black box: the spec scores dishes on the nutrient gap they
// close, and saying so is what makes a suggestion trustworthy.
test('explains why a dish was chosen when the planner has a reason', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(/closes the morning protein gap/i)).toBeInTheDocument()
})

test('marks a locked meal so it is clear it survives regeneration', async () => {
  renderScreen()

  const monday = await day('Monday')
  expect(monday.getByText('Locked')).toBeInTheDocument()
})

// A locked meal that could still be swapped away would make the lock meaningless.
test('a locked meal cannot be swapped', async () => {
  renderScreen()

  const monday = await day('Monday')
  const lockedRow = monday.getByText('Curd rice with poriyal').closest('li')
  expect(within(lockedRow!).getByRole('button', { name: /swap/i })).toBeDisabled()
})

// The planner never plans a day that has already ended, so a plan fetched
// mid-week has empty earlier days. Empty must read as a fact, not a failure.
test('says when a day has nothing planned', async () => {
  server.use(
    http.get(apiUrl('/plan/week'), () =>
      HttpResponse.json({
        ...PLAN_FIXTURE,
        days: [{ ...PLAN_FIXTURE.days[0], items: [] }, ...PLAN_FIXTURE.days.slice(1)],
      }),
    ),
  )
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(/nothing planned/i)).toBeInTheDocument()
})

/*
 * The backend answers 404 when there is no profile, because a plan is built from
 * targets and there are none yet. That is not an error; it means onboarding.
 */
test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(
    http.get(apiUrl('/plan/week'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: /set up your profile/i })).toHaveAttribute(
    'href',
    '/profile/about',
  )
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('no longer calls itself demo data', async () => {
  renderScreen()

  await day('Sunday')
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

// Solo tracking is the complete experience; there is nothing to reconcile alone.
test('a solo user sees no cooking view', async () => {
  renderScreen()

  await day('Sunday')
  expect(screen.queryByText(/cooking together/i)).not.toBeInTheDocument()
})

test('a household member sees where plans coincide on the selected day', async () => {
  server.use(
    http.get(apiUrl('/households/me'), () =>
      HttpResponse.json({
        id: 'h1',
        name: 'Home',
        members: [
          { user_id: 'u1', name: 'Sudev', email: 's@example.com', share_progress: true, share_health: false },
          { user_id: 'u2', name: 'Amma', email: 'a@example.com', share_progress: true, share_health: false },
        ],
      }),
    ),
    http.get(apiUrl('/plan/cooking'), () => HttpResponse.json(COOKING_FIXTURE)),
  )
  renderScreen()

  const cooking = within(await screen.findByRole('region', { name: /cooking together/i }))
  expect(cooking.getByText('Idli with sambar')).toBeInTheDocument()
  expect(cooking.getByText(/Sudev, Amma/)).toBeInTheDocument()
})
