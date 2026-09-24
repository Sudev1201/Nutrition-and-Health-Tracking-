import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { todayIso } from '../today/useToday'
import { HouseholdScreen } from './HouseholdScreen'
import type { HouseholdProgress, MemberProgress } from './useHousehold'

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

/*
 * Task 7's contract: you first, then the others. Counts of days only -- the
 * backend never sends a nutrient or a target, because a target is health data.
 */
const MY_WEEK: MemberProgress = {
  user_id: 'u-sudev',
  name: 'Sudev',
  is_me: true,
  shared: true,
  tracked_days: 3,
  nutrient_days_met: 41,
  nutrient_days_measured: 60,
}

const AMMAS_WEEK: MemberProgress = {
  user_id: 'u-amma',
  name: 'Amma',
  is_me: false,
  shared: true,
  tracked_days: 2,
  nutrient_days_met: 30,
  nutrient_days_measured: 38,
}

const NO_FIGURES = { tracked_days: null, nutrient_days_met: null, nutrient_days_measured: null }

const PROGRESS: HouseholdProgress = { start_date: '2026-09-20', members: [MY_WEEK, AMMAS_WEEK] }

function progressWith(amma: Partial<MemberProgress>): HouseholdProgress {
  return { ...PROGRESS, members: [MY_WEEK, { ...AMMAS_WEEK, ...amma }] }
}

/** The `start` of every progress request, in order. */
let progressStarts: string[] = []

beforeEach(() => {
  progressStarts = []
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

function stubProgress(body: HouseholdProgress = PROGRESS) {
  server.use(
    http.get(apiUrl('/households/progress'), ({ request }) => {
      progressStarts.push(new URL(request.url).searchParams.get('start') ?? '')
      return HttpResponse.json(body)
    }),
  )
}

function withHousehold(household = HOUSEHOLD) {
  server.use(http.get(apiUrl('/households/me'), () => HttpResponse.json(household)))
  stubProgress()
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

// --- this week's progress ------------------------------------------------------
//
// Weekly progress is shared by default, so whoever cooks can see how the week is
// going. What reaches the household is counts of days, never a target: a
// 1,500 mg sodium cap says hypertension as plainly as the diagnosis would.

test('shows each member’s week as counts of days, you first', async () => {
  withHousehold()
  renderScreen()

  const list = await screen.findByRole('list', { name: 'Household progress' })
  const rows = within(list).getAllByRole('listitem')
  expect(rows).toHaveLength(2)
  expect(rows[0]).toHaveTextContent('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(rows[1]).toHaveTextContent('Amma: on track 30 of 38 nutrient-days, 2 days logged')
})

test('asks for the week in progress, from its Sunday', async () => {
  withHousehold()
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(progressStarts).toHaveLength(1)
  const [start] = progressStarts
  // Both are plain calendar dates, parsed as UTC midnight: whole days apart.
  const daysIn = (Date.parse(todayIso()) - Date.parse(start)) / 86_400_000
  expect(new Date(Date.parse(start)).getUTCDay()).toBe(0)
  expect(daysIn).toBeGreaterThanOrEqual(0)
  expect(daysIn).toBeLessThan(7)
})

test.each([
  {
    state: 'not sharing progress',
    week: { shared: false, ...NO_FIGURES },
    text: 'Amma: not sharing progress',
  },
  {
    state: 'without a profile',
    week: NO_FIGURES,
    text: 'Amma: has not set up a profile yet',
  },
  {
    // Early in the week, or on its Sunday: today counts only once it is over.
    state: 'with no finished day logged',
    week: { tracked_days: 0, nutrient_days_met: 0, nutrient_days_measured: 0 },
    text: 'Amma: no days logged yet',
  },
  {
    state: 'one day in',
    week: { tracked_days: 1, nutrient_days_met: 12, nutrient_days_measured: 14 },
    text: 'Amma: on track 12 of 14 nutrient-days, 1 day logged',
  },
])('a member $state reads as “$text”', async ({ week, text }) => {
  withHousehold()
  stubProgress(progressWith(week))
  renderScreen()

  expect(await screen.findByText(text)).toBeInTheDocument()
})

// Your own row always shows you your figures. With sharing off it has to say
// that nobody else sees them, or it reads as if the household does.
test('says when your own figures are visible only to you', async () => {
  withHousehold() // Sudev shares no progress
  renderScreen()

  expect(await screen.findByText(/only you can see this/i)).toBeInTheDocument()
})

test('says nothing of the kind when you share your progress', async () => {
  withHousehold({
    ...HOUSEHOLD,
    members: HOUSEHOLD.members.map((member) => ({ ...member, share_progress: true })),
  })
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  expect(screen.queryByText(/only you can see this/i)).not.toBeInTheDocument()
})

test('changing what you share refreshes this week’s progress', async () => {
  withHousehold()
  server.use(
    http.patch(apiUrl('/households/visibility'), () =>
      HttpResponse.json({ share_progress: true, share_health: false }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev: on track 41 of 60 nutrient-days, 3 days logged')
  await userEvent.click(screen.getByRole('checkbox', { name: /share my daily progress/i }))

  await waitFor(() => expect(progressStarts).toHaveLength(2))
})

test('says so when this week’s progress cannot be loaded', async () => {
  withHousehold()
  server.use(
    http.get(apiUrl('/households/progress'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  expect(await screen.findByRole('alert')).toHaveTextContent(/progress could not be loaded/i)
})

// The household can go between the two requests -- left from another device,
// say. That is not an error; the household query catches up on its own.
test('shows no progress card when the household has gone', async () => {
  withHousehold()
  server.use(
    http.get(
      apiUrl('/households/progress'),
      () => new HttpResponse('You are not in a household yet', { status: 404 }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev Home')
  await waitFor(() => expect(screen.queryByText('This week so far')).not.toBeInTheDocument())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// The browser's calendar can reach a Sunday before the account's timezone does.
// That week has not begun where the account keeps time: not an error, and
// nothing to show yet.
test('shows no progress card for a week not yet begun where the account keeps time', async () => {
  withHousehold()
  server.use(
    http.get(
      apiUrl('/households/progress'),
      () => new HttpResponse('That week has not started yet', { status: 422 }),
    ),
  )
  renderScreen()

  await screen.findByText('Sudev Home')
  await waitFor(() => expect(screen.queryByText('This week so far')).not.toBeInTheDocument())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// Solo is the default and the full app. A card about other people's weeks has
// nothing to say to someone on their own, and must not ask for one.
test('a user on their own sees no progress card, and nothing asks for one', async () => {
  withoutHousehold()
  stubProgress()
  renderScreen()

  await screen.findByText(/tracking on your own/i)
  expect(screen.queryByText('This week so far')).not.toBeInTheDocument()
  expect(progressStarts).toEqual([])
})

// The old household's weeks are not yours to see once you have left, and the
// next household must not open on them while its own counts load.
test('leaving forgets the old household’s weeks', async () => {
  let calls = 0
  withHousehold()
  server.use(
    http.get(apiUrl('/households/progress'), async () => {
      calls += 1
      // The new household's counts never arrive, so any row shown after the
      // move can only have come from the old household.
      if (calls > 1) await delay('infinite')
      return HttpResponse.json(PROGRESS)
    }),
    http.post(apiUrl('/households/leave'), () => new HttpResponse(null, { status: 204 })),
    http.post(apiUrl('/households'), () =>
      HttpResponse.json(
        { id: 'h2', name: 'New Home', members: [HOUSEHOLD.members[1]] },
        { status: 201 },
      ),
    ),
  )
  renderScreen()

  await screen.findByText('Amma: on track 30 of 38 nutrient-days, 2 days logged')
  await userEvent.click(screen.getByRole('button', { name: /leave household/i }))
  await userEvent.type(await screen.findByLabelText('Household name'), 'New Home')
  await userEvent.click(screen.getByRole('button', { name: /create household/i }))

  expect(await screen.findByText('New Home')).toBeInTheDocument()
  expect(screen.getByText('This week so far')).toBeInTheDocument()
  expect(screen.queryByText(/^Amma:/)).not.toBeInTheDocument()
})
