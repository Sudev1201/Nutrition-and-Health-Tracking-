import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { WEIGHT_FIXTURE } from '../mocks/fixtures/more'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { WeightScreen } from './WeightScreen'
import type { WeightTrend } from './types'

let posted: unknown = null
let deleted: string | null = null

function stubTrend(trend: WeightTrend) {
  server.use(http.get(apiUrl('/weight'), () => HttpResponse.json(trend)))
}

beforeEach(() => {
  posted = null
  deleted = null
  server.use(
    http.get(apiUrl('/weight'), () => HttpResponse.json(WEIGHT_FIXTURE)),
    http.post(apiUrl('/weight'), async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json(WEIGHT_FIXTURE, { status: 201 })
    }),
    http.delete(apiUrl('/weight/:date'), ({ params }) => {
      deleted = params.date as string
      return new HttpResponse(null, { status: 204 })
    }),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WeightScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('shows the trend from the real endpoint, with no demo banner', async () => {
  renderScreen()

  expect(await screen.findByRole('rowheader', { name: '16 Aug 2026' })).toBeInTheDocument()
  expect(screen.getByText('losing about 0.4 kg a week')).toBeInTheDocument()
  expect(screen.getByText('losing about 0.1 kg a week')).toBeInTheDocument()
  expect(screen.getByText('2,020 kcal a day')).toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

test('sends the weigh-in with its date, and clears the field once saved', async () => {
  renderScreen()

  const field = await screen.findByLabelText('Weight in kg')
  expect(screen.getByLabelText('Date')).toHaveValue(todayIso())
  await userEvent.type(field, '74.0')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(posted).toEqual({ weight_kg: 74, date: todayIso() }))
  await waitFor(() => expect(field).toHaveValue(''))
})

// The energy equations are weight-based: a typo would quietly skew every target.
test('will not save an implausible weight', async () => {
  renderScreen()

  await userEvent.type(await screen.findByLabelText('Weight in kg'), '7.4')

  expect(screen.getByRole('alert')).toHaveTextContent(/between 20 and 300/)
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
})

test('keeps what was typed when the save fails', async () => {
  server.use(http.post(apiUrl('/weight'), () => new HttpResponse('boom', { status: 500 })))
  renderScreen()

  const field = await screen.findByLabelText('Weight in kg')
  await userEvent.type(field, '74')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be saved/)
  expect(field).toHaveValue('74')
})

test('explains a calorie target that moved, and since when', async () => {
  renderScreen()

  expect(await screen.findByRole('heading', { name: /calorie target moved/i })).toBeInTheDocument()
  expect(screen.getByText('-90 kcal')).toBeInTheDocument()
  expect(screen.getByText(/since 16 Aug 2026/)).toBeInTheDocument()
  expect(screen.getByText(/moves down a bounded step/)).toBeInTheDocument()
})

test('says nothing about an adjustment when there is none', async () => {
  stubTrend({ ...WEIGHT_FIXTURE, adjustment: null })
  renderScreen()

  await screen.findByRole('rowheader', { name: '16 Aug 2026' })
  expect(screen.queryByRole('heading', { name: /calorie target moved/i })).not.toBeInTheDocument()
})

test('a weigh-in can be removed', async () => {
  renderScreen()

  await userEvent.click(
    await screen.findByRole('button', { name: 'Remove the weigh-in on 16 Aug 2026' }),
  )

  await waitFor(() => expect(deleted).toBe('2026-08-16'))
})

test('draws no trend line from a single weigh-in', async () => {
  stubTrend({
    ...WEIGHT_FIXTURE,
    weigh_ins: [{ date: '2026-08-16', weight_kg: 65 }],
    smoothed_kg: 65,
    observed_kg_per_week: null,
    adjustment: null,
    note: 'Your trend is read from three weigh-ins across at least two weeks. Weighing in once a week is enough.',
  })
  renderScreen()

  expect(await screen.findByText(/appears after your second weigh-in/)).toBeInTheDocument()
  expect(screen.getByText('Not enough weigh-ins yet')).toBeInTheDocument()
  expect(screen.getByText(/read from three weigh-ins/)).toBeInTheDocument()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(http.get(apiUrl('/weight'), () => new HttpResponse('no profile', { status: 404 })))
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
