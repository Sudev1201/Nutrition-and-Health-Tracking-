import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { LogScreen } from './LogScreen'
import type { NewDiaryEntry } from './types'

const RESULTS = [
  { id: 'd-pongal', kind: 'dish', name: 'Ven Pongal', source: 'authored', is_editable: true },
]

/** A measure seeded for this dish, plus a generic one that is only a guess. */
const MEASURES = {
  measures: [
    { name: 'bowl', grams: 200, is_default: true, is_approximate: false, unit: 'g' },
    { name: 'cup', grams: 240, is_default: false, is_approximate: true, unit: 'g' },
  ],
}

let posted: NewDiaryEntry | null = null

beforeEach(() => {
  posted = null
  server.use(
    http.get(apiUrl('/foods/search'), () => HttpResponse.json(RESULTS)),
    http.get(apiUrl('/foods/dish/d-pongal/measures'), () => HttpResponse.json(MEASURES)),
    http.post(apiUrl('/diary/entries'), async ({ request }) => {
      posted = (await request.json()) as NewDiaryEntry
      return HttpResponse.json({ id: 'e-new' }, { status: 201 })
    }),
  )
})

function renderScreen(path = '/log') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <LogScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Search for a food and open the portion sheet for the first result. */
async function pickPongal() {
  fireEvent.change(screen.getByRole('searchbox', { name: /search/i }), {
    target: { value: 'pongal' },
  })
  await userEvent.click(await screen.findByRole('button', { name: /add ven pongal/i }))
  // The sheet defaults to the dish's own measure once they load.
  await screen.findByRole('combobox', { name: /measure/i })
}

// Today's meal rows link to /log?slot=dinner. Landing on the wrong slot means
// silently logging dinner as breakfast.
test('starts on the slot the link named', () => {
  renderScreen('/log?slot=dinner')

  expect(screen.getByRole('combobox', { name: /meal/i })).toHaveValue('dinner')
})

test('falls back to breakfast when no slot is named', () => {
  renderScreen()

  expect(screen.getByRole('combobox', { name: /meal/i })).toHaveValue('breakfast')
})

/*
 * A portion is two units at once: the household measure the user thinks in, and
 * the absolute the nutrient tables need. The picker keeps them linked.
 */

test('opens on the measure seeded for this dish', async () => {
  renderScreen()
  await pickPongal()

  expect(screen.getByRole('combobox', { name: /measure/i })).toHaveValue('bowl')
})

test('defaults the absolute to one whole measure', async () => {
  renderScreen()
  await pickPongal()

  expect(screen.getByRole('textbox', { name: /weigh it/i })).toHaveValue('200')
})

test('half a measure halves the absolute', async () => {
  renderScreen()
  await pickPongal()

  await userEvent.selectOptions(screen.getByRole('combobox', { name: /how much/i }), '0.5')

  expect(screen.getByRole('textbox', { name: /weigh it/i })).toHaveValue('100')
})

test('logs the measure and quantity the user chose', async () => {
  renderScreen('/log?slot=dinner')
  await pickPongal()

  await userEvent.selectOptions(screen.getByRole('combobox', { name: /how much/i }), '0.5')
  await userEvent.click(screen.getByRole('button', { name: /add to/i }))

  await waitFor(() => expect(posted).not.toBeNull())
  expect(posted).toMatchObject({
    slot: 'dinner',
    food_id: 'd-pongal',
    measure_name: 'bowl',
    quantity: 0.5,
  })
})

// The server resolves the weight from its own figures, so sending a stale one
// alongside the measure could contradict it.
test('sends no weight when a household measure was chosen', async () => {
  renderScreen()
  await pickPongal()

  await userEvent.click(screen.getByRole('button', { name: /add to/i }))

  await waitFor(() => expect(posted).not.toBeNull())
  expect(posted?.grams).toBeNull()
})

test('a weighed portion is sent as a weight with no measure', async () => {
  renderScreen()
  await pickPongal()

  const absolute = screen.getByRole('textbox', { name: /weigh it/i })
  await userEvent.clear(absolute)
  await userEvent.type(absolute, '175')
  await userEvent.click(screen.getByRole('button', { name: /add to/i }))

  await waitFor(() => expect(posted).not.toBeNull())
  expect(posted?.grams).toBe(175)
  expect(posted?.measure_name).toBeNull()
})

// A generic measure's weight is a general figure, so the user is told before
// they log rather than discovering it in the weekly report.
test('warns that a generic measure is only approximate', async () => {
  renderScreen()
  await pickPongal()

  await userEvent.selectOptions(screen.getByRole('combobox', { name: /measure/i }), 'cup')

  expect(screen.getByText(/general figure, not one measured for this food/i)).toBeInTheDocument()
})

test('marks an entry as estimated when the user says it is a guess', async () => {
  renderScreen()
  await pickPongal()

  await userEvent.click(screen.getByRole('checkbox', { name: /estimate/i }))
  await userEvent.click(screen.getByRole('button', { name: /add to/i }))

  await waitFor(() => expect(posted).not.toBeNull())
  expect(posted?.is_estimated).toBe(true)
})

test('entries are measured unless the user says otherwise', async () => {
  renderScreen()
  await pickPongal()

  await userEvent.click(screen.getByRole('button', { name: /add to/i }))

  await waitFor(() => expect(posted).not.toBeNull())
  expect(posted?.is_estimated).toBe(false)
})
