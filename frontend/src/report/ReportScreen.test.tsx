import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { IN_PROGRESS_REPORT_FIXTURE, REPORT_FIXTURE } from '../mocks/fixtures/report'
import { server } from '../mocks/server'
import { ReportScreen } from './ReportScreen'
import type { WeeklyReport } from './types'
import { addDays, lastCompleteWeekStart } from './useReport'

/*
 * Wednesday 26 August 2026. This week began on Sunday the 23rd, so the last
 * complete week, the one the screen opens on, is 16 to 22 August: the fixture's
 * week. Only `Date` is faked, so React Query, MSW and user-event keep their real
 * timers.
 */
const NOW = new Date(2026, 7, 26, 10, 0)

let requested: string[] = []

function stubReport(report: WeeklyReport) {
  server.use(http.get(apiUrl('/reports/week'), () => HttpResponse.json(report)))
}

function stubStatus(status: number) {
  server.use(http.get(apiUrl('/reports/week'), () => new HttpResponse('error', { status })))
}

beforeEach(() => {
  requested = []
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  server.use(
    http.get(apiUrl('/reports/week'), ({ request }) => {
      const start = new URL(request.url).searchParams.get('start') ?? ''
      requested.push(start)
      const inProgress = start === IN_PROGRESS_REPORT_FIXTURE.start_date
      return HttpResponse.json(inProgress ? IN_PROGRESS_REPORT_FIXTURE : REPORT_FIXTURE)
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReportScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** The fixture week has loaded: its meals figure is on screen. */
async function loaded() {
  await screen.findByText('29 of 35')
}

/** A row of the nutrients table. */
function nutrientRow(name: string) {
  return within(screen.getByRole('rowheader', { name }).closest('tr')!)
}

/** A row of the table behind the energy chart. */
async function dayRow(weekday: string) {
  const table = await screen.findByRole('table', { name: /energy each day/i })
  return within(within(table).getByRole('rowheader', { name: weekday }).closest('tr')!)
}

// --- which week ----------------------------------------------------------------------

test('the last complete week is the one before this week', () => {
  // Thursday 24 September 2026. This week began on Sunday the 20th.
  expect(lastCompleteWeekStart(new Date(2026, 8, 24, 9, 0))).toBe('2026-09-13')
})

test('on a Sunday, the week just ended is the last complete one', () => {
  expect(lastCompleteWeekStart(new Date(2026, 8, 20, 9, 0))).toBe('2026-09-13')
})

test('late on a Saturday, the week is not complete yet', () => {
  expect(lastCompleteWeekStart(new Date(2026, 8, 19, 23, 30))).toBe('2026-09-06')
})

test('weeks are counted across a month and across a year', () => {
  expect(lastCompleteWeekStart(new Date(2026, 7, 3, 9, 0))).toBe('2026-07-26')
  expect(addDays('2026-12-27', 7)).toBe('2027-01-03')
})

test('opens on the last complete week, from the real endpoint', async () => {
  renderScreen()

  await loaded()
  expect(requested).toEqual(['2026-08-16'])
  expect(screen.getByRole('heading', { name: '16 Aug 2026 – 22 Aug 2026' })).toBeInTheDocument()
  expect(screen.queryByText('In progress')).not.toBeInTheDocument()
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

test('Previous week asks for the week before', async () => {
  renderScreen()
  await loaded()

  await userEvent.click(screen.getByRole('button', { name: 'Previous week' }))

  expect(
    await screen.findByRole('heading', { name: '9 Aug 2026 – 15 Aug 2026' }),
  ).toBeInTheDocument()
  await waitFor(() => expect(requested).toEqual(['2026-08-16', '2026-08-09']))
})

test('Next week goes as far as the week in progress, and no further', async () => {
  renderScreen()
  await loaded()
  expect(screen.getByRole('button', { name: 'Next week' })).toBeEnabled()

  await userEvent.click(screen.getByRole('button', { name: 'Next week' }))

  expect(await screen.findByText('In progress')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '23 Aug 2026 – 29 Aug 2026' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next week' })).toBeDisabled()
  expect(requested).toEqual(['2026-08-16', '2026-08-23'])
})

test('a week in progress counts only the days that are over', async () => {
  renderScreen()
  await loaded()

  await userEvent.click(screen.getByRole('button', { name: 'Next week' }))

  expect(await screen.findByText(/count once they are over/)).toBeInTheDocument()
  // Sunday to Tuesday are over, and two of them were logged.
  expect(screen.getByText('2 of 3')).toBeInTheDocument()
  expect(screen.getByText('days over so far')).toBeInTheDocument()
  expect((await dayRow('Wed')).getByText('Today, not over yet')).toBeInTheDocument()
  expect((await dayRow('Thu')).getByText('Still to come')).toBeInTheDocument()
})

// --- the week's account ----------------------------------------------------------------

test('accounts for every meal slot of the week, and for the plan', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('6 of 7')).toBeInTheDocument()
  // Skipped is accounted for; only the slots with neither food nor a skip were missed.
  expect(screen.getByText('26 logged, 3 skipped, 6 missed')).toBeInTheDocument()
  expect(screen.getByText('17 of 28')).toBeInTheDocument()
})

test('says nothing about a plan when the week had none', async () => {
  stubReport({ ...REPORT_FIXTURE, plan: null })
  renderScreen()
  await loaded()

  expect(screen.queryByText('Plan followed')).not.toBeInTheDocument()
})

// A week largely eaten out must not be presented with false precision.
test('keeps estimated energy apart from measured energy', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('9,160 kcal')).toBeInTheDocument()
  expect(screen.getByText('2,980 kcal')).toBeInTheDocument()
  expect(screen.getByText('25% of the week’s energy, kept apart')).toBeInTheDocument()
})

// --- nutrients -------------------------------------------------------------------------

test('counts days met over the days that measured the nutrient', async () => {
  renderScreen()
  await loaded()

  expect(nutrientRow('Calcium').getByText('1 of 6')).toBeInTheDocument()
  // Fibre was measured on five of the six days logged.
  expect(nutrientRow('Dietary fibre').getByText('1 of 5')).toBeInTheDocument()
})

test('judges the week against its summed EAR and target, as Today judges a day', async () => {
  renderScreen()
  await loaded()

  // 296.4 g is short of the week's 323.7 g target but past its 257.4 g EAR.
  expect(nutrientRow('Protein').getByText('on target')).toBeInTheDocument()
  expect(nutrientRow('Calcium').getByText('under target')).toBeInTheDocument()
  expect(nutrientRow('Vitamin B12').getByText('over target')).toBeInTheDocument()
  // A ceiling's own figure is its limit: 14,820 mg against 12,000 mg.
  expect(nutrientRow('Sodium').getByText('past the upper limit')).toBeInTheDocument()
})

test('notes days past the upper limit apart from the week’s standing', async () => {
  stubReport({
    ...REPORT_FIXTURE,
    nutrients: REPORT_FIXTURE.nutrients.map((nutrient) => {
      if (nutrient.code === 'calcium') return { ...nutrient, days_over_limit: 2 }
      if (nutrient.code === 'iron') return { ...nutrient, days_over_limit: 1 }
      return nutrient
    }),
  })
  renderScreen()
  await loaded()

  expect(nutrientRow('Calcium').getByText('2 days over the limit')).toBeInTheDocument()
  expect(nutrientRow('Iron').getByText('1 day over the limit')).toBeInTheDocument()
  expect(nutrientRow('Protein').queryByText(/over the limit/)).not.toBeInTheDocument()
})

test('says how much of the food a figure speaks for', async () => {
  renderScreen()
  await loaded()

  expect(
    nutrientRow('Vitamin B12').getByText('Measured for 62% of what you ate'),
  ).toBeInTheDocument()
  expect(nutrientRow('Calcium').queryByText(/Measured for/)).not.toBeInTheDocument()
})

test('shows energy totals in whole kilocalories', async () => {
  renderScreen()
  await loaded()

  expect(nutrientRow('Energy').getByText('12,140')).toBeInTheDocument()
  expect(nutrientRow('Energy').getByText('12,002 kcal')).toBeInTheDocument()
})

// --- what could not be made up, and what to eat -----------------------------------------

/*
 * The report must show what could NOT be made up. Silently dropping an expired
 * shortfall would present a worse week as a better one, which is the exact
 * dishonesty the ledger's expiry record exists to prevent.
 */
test('reports shortfalls the ledger could not make up, and why', async () => {
  renderScreen()
  await loaded()

  expect(screen.getByText('Calcium — 1,240 mg')).toBeInTheDocument()
  expect(screen.getByText('Beyond the 30% a day can carry, so it expired.')).toBeInTheDocument()
  expect(screen.getByText('Dietary fibre — 22.6 g')).toBeInTheDocument()
  expect(screen.getByText('Beyond the 25% a day can carry, so it expired.')).toBeInTheDocument()
  expect(
    screen.getByText('Protein has no storage pool, so a short day is not carried forward.'),
  ).toBeInTheDocument()
})

test('suggests dishes for what fell short', async () => {
  renderScreen()
  await loaded()

  expect(
    screen.getByText(
      'Calcium fell short this week. ' +
        'Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam.',
    ),
  ).toBeInTheDocument()
  const dishes = within(screen.getByRole('list', { name: 'Dishes for Calcium' }))
  expect(dishes.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    'Ragi mudde',
    'Curd rice',
    'Moong dal payasam',
  ])
})

test('says so when nothing expired and nothing needs suggesting', async () => {
  stubReport({ ...REPORT_FIXTURE, uncompensated: [], suggestions: [] })
  renderScreen()
  await loaded()

  expect(screen.getByText('No shortfall expired this week.')).toBeInTheDocument()
  expect(
    screen.getByText('No nutrient fell short on enough measured days to suggest a change.'),
  ).toBeInTheDocument()
})

// --- the energy chart --------------------------------------------------------------------

/*
 * A chart is unreadable to a screen reader, and Recharts renders SVG with no
 * text alternative. The same series is therefore also exposed as a table.
 */
test('the energy chart’s figures are a table, each day against its own target', async () => {
  renderScreen()

  const sunday = await dayRow('Sun')
  expect(sunday.getByText('2,240 kcal')).toBeInTheDocument()
  expect(sunday.getByText('2,105 kcal')).toBeInTheDocument()
  // Thursday's weigh-in stepped the target down from that day on.
  const thursday = await dayRow('Thu')
  expect(thursday.getByText('2,310 kcal')).toBeInTheDocument()
  expect(thursday.getByText('1,895 kcal')).toBeInTheDocument()
})

test('a day with nothing logged is not shown as a day of eating nothing', async () => {
  renderScreen()

  const tuesday = await dayRow('Tue')
  expect(tuesday.getByText('Nothing logged')).toBeInTheDocument()
  expect(tuesday.queryByText('0 kcal')).not.toBeInTheDocument()
})

// --- nothing to show -----------------------------------------------------------------------

test('an empty week says so instead of showing a week of zeros', async () => {
  stubReport({
    ...REPORT_FIXTURE,
    tracked_days: 0,
    slots: { logged: 0, skipped: 0, expected: 35 },
    measured_kcal: 0,
    estimated_kcal: 0,
    plan: null,
    days: REPORT_FIXTURE.days.map((day) => ({
      ...day,
      state: 'untracked' as const,
      energy_kcal: 0,
    })),
    nutrients: [],
    uncompensated: [],
    suggestions: [],
  })
  renderScreen()

  expect(await screen.findByText('Nothing was logged this week')).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  // An earlier week may have more, so the way back stays open.
  expect(screen.getByRole('button', { name: 'Previous week' })).toBeEnabled()
})

test('sends a user with no profile to onboarding rather than showing an error', async () => {
  stubStatus(404)
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// The browser's calendar can reach a Sunday before the account's timezone does.
test('says so when the week has not started where the account keeps time', async () => {
  stubStatus(422)
  renderScreen()

  expect(await screen.findByText('That week has not started yet')).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('says when the report could not be loaded, and keeps the way to other weeks', async () => {
  stubStatus(500)
  renderScreen()

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/)
  expect(screen.getByRole('button', { name: 'Previous week' })).toBeEnabled()
})
