import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { DIARY_FIXTURE } from '../mocks/fixtures/diary'
import { TODAY_FIXTURE } from '../mocks/fixtures/today'
import { server } from '../mocks/server'
import { TodayScreen } from './TodayScreen'

/*
 * `/targets/today` and `/diary` are real endpoints now, so these stub them
 * per-test rather than relying on default handlers. The fixtures are kept
 * because they exercise the awkward states — a carry from Friday, sodium past
 * its ceiling, a B12 surplus with no limit to breach — which real seed data
 * would not reliably produce.
 */
beforeEach(() => {
  server.use(
    http.get(apiUrl('/targets/today'), () => HttpResponse.json(TODAY_FIXTURE)),
    http.get(apiUrl('/diary'), () => HttpResponse.json(DIARY_FIXTURE)),
    http.get(apiUrl('/profile/baseline'), () =>
      HttpResponse.json({
        has_usual_intake: true,
        usual_energy_kcal: 1850,
        target_energy_kcal: 2110,
        difference_kcal: -260,
        implausible: false,
        note: null,
      }),
    ),
  )
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TodayScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('leads with energy against today’s target', async () => {
  renderScreen()

  expect(await screen.findByText('Energy')).toBeInTheDocument()
  expect(await screen.findByText(/1,420/)).toBeInTheDocument()
})

test('lists micronutrients with what has been consumed', async () => {
  renderScreen()

  expect(await screen.findByText('Calcium')).toBeInTheDocument()
  expect(await screen.findByText('410 / 1,180 mg')).toBeInTheDocument()
})

// The compensation ledger is the app's central idea; if the user cannot see that
// today's calcium target is raised because of Friday, it may as well not exist.
test('shows what the ledger carried into today, and from when', async () => {
  renderScreen()

  expect(await screen.findByText('+180 mg carried from Friday')).toBeInTheDocument()
})

test('surfaces a conflict between conditions rather than hiding it', async () => {
  renderScreen()

  expect(await screen.findByText(/hypertension and symptomatic hypotension/i)).toBeInTheDocument()
})

test('surfaces the levothyroxine timing note', async () => {
  renderScreen()

  expect(await screen.findByText(/including milk coffee/i)).toBeInTheDocument()
})

/*
 * The counter-intuitive rule, locked in. ICMR deliberately set NO upper limit for
 * B12, so 7.5 µg against a 2.2 µg RDA -- 340% -- must not be flagged. Sodium at
 * 2,680 mg against a 2,000 mg ceiling is the only alarm on this day. A future
 * change that "helpfully" warns on any large surplus breaks this test.
 */
test('raises an upper-limit alarm only for the nutrient that has one', async () => {
  renderScreen()

  await screen.findByText('Sodium')
  expect(screen.getAllByText('past the upper limit')).toHaveLength(1)
})

test('shows a large B12 surplus as over target, not as an alarm', async () => {
  renderScreen()

  await screen.findByText('Vitamin B12')
  expect(screen.getAllByText('over target').length).toBeGreaterThan(0)
})

test('shows all five meal slots', async () => {
  renderScreen()

  for (const label of ['Breakfast', 'Mid-morning snack', 'Lunch', 'Evening snack', 'Dinner']) {
    expect(await screen.findByText(label)).toBeInTheDocument()
  }
})

test('distinguishes a skipped slot from one still to be logged', async () => {
  renderScreen()

  expect(await screen.findByText('Skipped')).toBeInTheDocument()
})

// Restaurant portions are guesses, and the weekly report separates them from
// measured intake. That distinction has to start at the point of logging.
test('marks an estimated entry as estimated', async () => {
  renderScreen()

  expect(await screen.findByText('Estimated')).toBeInTheDocument()
})

/*
 * The backend answers `/targets/today` with 404 when there is no profile, because
 * nothing can be computed without one. That is not an error to apologise for --
 * it means the user has not onboarded, so the screen has to send them there.
 */
test('sends a user with no profile to onboarding rather than showing an error', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: /set up your profile/i })).toHaveAttribute(
    'href',
    '/profile',
  )
})

test('does not present a missing profile as something that went wrong', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  await screen.findByRole('link', { name: /set up your profile/i })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// A genuine failure still has to read as one.
test('reports a real failure as an error', async () => {
  server.use(
    http.get(apiUrl('/targets/today'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  expect(await screen.findByRole('alert')).toBeInTheDocument()
})


/*
 * The app used to ask what the user normally eats and then never say what it added
 * up to. The baseline is the answer: usual intake against the computed target.
 */
test('shows what a usual day adds up to against the target', async () => {
  renderScreen()

  expect(await screen.findByText(/where you are starting from/i)).toBeInTheDocument()
  expect(await screen.findByText(/1,850 kcal/)).toBeInTheDocument()
  expect(await screen.findByText(/260 kcal below/)).toBeInTheDocument()
})

test('offers to collect a usual day when there is not one yet', async () => {
  server.use(
    http.get(apiUrl('/profile/baseline'), () =>
      HttpResponse.json({
        has_usual_intake: false,
        usual_energy_kcal: null,
        target_energy_kcal: 2110,
        difference_kcal: null,
        implausible: false,
        note: null,
      }),
    ),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: /add a usual day/i })).toBeInTheDocument()
})
