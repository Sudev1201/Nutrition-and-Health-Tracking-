import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { CYCLE_FIXTURE } from '../mocks/fixtures/more'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { CycleScreen } from './CycleScreen'
import type { CycleState } from './types'

let patched: unknown = null
let saved: { date: string; body: unknown } | null = null
let answered: unknown = null
let cleared: string | null = null
let erased = false

function stubState(state: CycleState) {
  server.use(http.get(apiUrl('/cycle'), () => HttpResponse.json(state)))
}

// `/cycle` is a real endpoint now, so every request is stubbed here and nothing
// falls through to a default handler.
beforeEach(() => {
  patched = null
  saved = null
  answered = null
  cleared = null
  erased = false
  server.use(
    http.get(apiUrl('/cycle'), () => HttpResponse.json(CYCLE_FIXTURE)),
    http.patch(apiUrl('/cycle'), async ({ request }) => {
      patched = await request.json()
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
    http.delete(apiUrl('/cycle'), () => {
      erased = true
      return new HttpResponse(null, { status: 204 })
    }),
    http.put(apiUrl('/cycle/days/:date'), async ({ request, params }) => {
      saved = { date: params.date as string, body: await request.json() }
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
    http.delete(apiUrl('/cycle/days/:date'), ({ params }) => {
      cleared = params.date as string
      return new HttpResponse(null, { status: 204 })
    }),
    http.post(apiUrl('/cycle/screening'), async ({ request }) => {
      answered = await request.json()
      return HttpResponse.json(CYCLE_FIXTURE)
    }),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CycleScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const OFF: CycleState = { ...CYCLE_FIXTURE, enabled: false, days: [], coaching: [] }

test('is off until the user turns it on', async () => {
  stubState(OFF)
  renderScreen()

  expect(await screen.findByRole('switch', { name: /track my cycle/i })).not.toBeChecked()
  expect(screen.queryByText(/keep coffee and tea/i)).not.toBeInTheDocument()
})

test('turning it on sends the switch', async () => {
  stubState(OFF)
  renderScreen()

  await userEvent.click(await screen.findByRole('switch', { name: /track my cycle/i }))

  await waitFor(() => expect(patched).toEqual({ enabled: true }))
})

test('shows the coaching notes once enabled, with no demo banner', async () => {
  renderScreen()

  expect(await screen.findByText(/keep coffee and tea an hour away/i)).toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

/*
 * THE COUNTER-INTUITIVE RULE, LOCKED IN.
 *
 * ICMR's 29 mg/day iron figure for women ALREADY averages menstrual blood loss
 * across the whole cycle. Raising iron during a period double-counts the same
 * loss. The giveaway is that the pregnancy RDA (27 mg) is LOWER than the
 * non-pregnant one. This screen must therefore say the target does not move —
 * a future change that "helpfully" raises iron on bleed days breaks this test,
 * and `backend/tests/test_cycle_api.py` locks the number itself.
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
  stubState({
    ...CYCLE_FIXTURE,
    referral: { reason: 'You reported soaking through a pad or tampon in two hours or less.' },
  })
  renderScreen()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent(/clinician/i)
  expect(alert).toHaveTextContent(/soaking through a pad/i)
  expect(alert).toHaveTextContent(/adolescents/i)
})

test('is not offered to a male profile, and says why', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'not-female' })
  renderScreen()

  expect(await screen.findByText(/for profiles set to female/i)).toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
})

test('after menopause, says any bleeding should be checked by a clinician', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'postmenopausal' })
  renderScreen()

  expect(await screen.findByText(/should be checked by a clinician/i)).toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
})

test('logs a day with its flow and symptoms', async () => {
  renderScreen()

  await userEvent.selectOptions(await screen.findByLabelText('Bleeding'), 'heavy')
  await userEvent.click(screen.getByRole('checkbox', { name: 'Cramps' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save day' }))

  await waitFor(() =>
    expect(saved).toEqual({ date: todayIso(), body: { flow: 'heavy', symptoms: ['cramps'] } }),
  )
})

test('will not save a day with nothing in it', async () => {
  renderScreen()

  expect(await screen.findByRole('button', { name: 'Save day' })).toBeDisabled()
})

// PUT /cycle/days/{date} replaces the whole day, so picking a date that already
// has an entry must show what is already logged, or saving would silently wipe
// it -- and, for a bleed day, the coaching that depends on it.
test('picking an already-logged date prefills its flow and symptoms', async () => {
  renderScreen()

  fireEvent.change(await screen.findByLabelText('Date'), { target: { value: '2026-08-15' } })

  expect(await screen.findByLabelText('Bleeding')).toHaveValue('heavy')
  expect(screen.getByRole('checkbox', { name: 'Cramps' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Bloating' })).not.toBeChecked()
  expect(screen.getByRole('button', { name: 'Update day' })).toBeInTheDocument()
})

test('sends the screening answers', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('checkbox', { name: /soak through a pad/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Save answers' }))

  await waitFor(() =>
    expect(answered).toEqual({
      soaks_within_two_hours: true,
      longer_than_seven_days: false,
      large_clots: false,
      flooding: false,
      date: todayIso(),
    }),
  )
})

test('shows when the last period started, from logged days only', async () => {
  renderScreen()

  expect(await screen.findByText(/last period started on 14 Aug 2026/i)).toBeInTheDocument()
  expect(screen.getByText(/heavy flow, cramps/i)).toBeInTheDocument()
})

test('a logged day can be removed', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove 16 Aug 2026' }))

  await waitFor(() => expect(cleared).toBe('2026-08-16'))
})

test('deleting the history asks first', async () => {
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Delete my cycle history' }))
  expect(erased).toBe(false)

  await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))
  await waitFor(() => expect(erased).toBe(true))
})

test('history hidden by a profile change can still be erased', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'postmenopausal', has_history: true })
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Delete my cycle history' }))
  await userEvent.click(screen.getByRole('button', { name: 'Delete everything' }))
  await waitFor(() => expect(erased).toBe(true))
})

test('offers no erase when nothing is stored', async () => {
  stubState({ ...OFF, eligible: false, ineligible_reason: 'not-female', has_history: false })
  renderScreen()

  await screen.findByText(/for profiles set to female/i)
  expect(screen.queryByRole('button', { name: 'Delete my cycle history' })).not.toBeInTheDocument()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(http.get(apiUrl('/cycle'), () => new HttpResponse('no profile', { status: 404 })))
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
})
