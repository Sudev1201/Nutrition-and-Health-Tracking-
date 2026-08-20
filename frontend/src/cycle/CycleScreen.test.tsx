import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { CYCLE_FIXTURE } from '../mocks/fixtures/more'
import { server } from '../mocks/server'
import { CycleScreen } from './CycleScreen'

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <CycleScreen />
    </QueryClientProvider>,
  )
}

test('is off until the user turns it on', async () => {
  server.use(
    http.get(apiUrl('/cycle'), () =>
      HttpResponse.json({ ...CYCLE_FIXTURE, enabled: false, logs: [], coaching: [] }),
    ),
  )
  renderScreen()

  expect(await screen.findByRole('switch', { name: /track my cycle/i })).not.toBeChecked()
  expect(screen.queryByText(/keep coffee and tea/i)).not.toBeInTheDocument()
})

test('shows the coaching notes once enabled', async () => {
  renderScreen()

  expect(await screen.findByText(/keep coffee and tea an hour away/i)).toBeInTheDocument()
})

/*
 * THE COUNTER-INTUITIVE RULE, LOCKED IN.
 *
 * ICMR's 29 mg/day iron figure for women ALREADY averages menstrual blood loss
 * across the whole cycle. Raising iron during a period double-counts the same
 * loss. The giveaway is that the pregnancy RDA (27 mg) is LOWER than the
 * non-pregnant one. This screen must therefore say the target does not move —
 * a future change that "helpfully" raises iron on bleed days breaks this test.
 */
test('states plainly that logging a period does not raise the iron target', async () => {
  renderScreen()

  expect(await screen.findByText(/iron target does not change/i)).toBeInTheDocument()
})

/*
 * The second locked rule. The luteal rise in resting expenditure is about 32
 * kcal/day once anovulatory cycles are accounted for — inside the noise of
 * day-to-day intake — and telling users the app expects them to eat more
 * manufactures exactly the logging pattern that would appear to validate it.
 */
test('states plainly that cycle phase does not change the calorie target', async () => {
  renderScreen()

  expect(await screen.findByText(/calorie target does not change/i)).toBeInTheDocument()
})

// Evidence is labelled, not laundered.
test('labels how strong the evidence behind each suggestion is', async () => {
  renderScreen()

  expect(await screen.findByText('Strong evidence')).toBeInTheDocument()
})

// Heavy bleeding gets a clinician, not a nutrient tweak: roughly 1 in 5
// adolescents with heavy bleeding has an underlying bleeding disorder.
test('refers heavy bleeding to a clinician rather than adjusting nutrients', async () => {
  server.use(
    http.get(apiUrl('/cycle'), () =>
      HttpResponse.json({
        ...CYCLE_FIXTURE,
        referral: { reason: 'You reported soaking a pad within two hours.' },
      }),
    ),
  )
  renderScreen()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(/clinician/i)
  expect(alert).toHaveTextContent(/soaking a pad/i)
})
