import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import { PlanScreen } from './PlanScreen'

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <PlanScreen />
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

test('says plainly that the plan is demo data', async () => {
  renderScreen()

  expect(await screen.findByRole('note')).toHaveTextContent(/demo data/i)
})
