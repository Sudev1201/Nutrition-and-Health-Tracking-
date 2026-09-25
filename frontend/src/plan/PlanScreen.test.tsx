import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import {
  COOKING_FIXTURE,
  PLAN_FIXTURE,
  POLISHED_PLAN_FIXTURE,
  PONGAL_TEXT,
  SAMBAR_RICE_TEXT,
} from '../mocks/fixtures/plan'
import { server } from '../mocks/server'
import type { LlmSettings } from '../settings/types'
import { PlanScreen } from './PlanScreen'
import type { WeekPlan } from './types'
import { weekStartIso } from './usePlan'

/** No key saved: the screen offers no descriptions. */
const NO_KEY: LlmSettings = {
  available: true,
  provider: null,
  model: null,
  key_hint: null,
  status: 'none',
  models: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
}
const KEY_SAVED: LlmSettings = {
  ...NO_KEY,
  provider: 'anthropic',
  model: 'claude-opus-5',
  key_hint: 'WXYZ',
  status: 'ok',
}

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
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(NO_KEY)),
  )
})

function renderScreen(
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PlanScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...rendered, queryClient }
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

// A regenerate replaces every unlocked item, so a swap or lock sent while it runs
// targets a row that is being replaced -- the server answered 500 for that.
test('swapping and locking wait while the week regenerates', async () => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.post(apiUrl('/plan/week/regenerate'), async () => {
      await held
      return HttpResponse.json(PLAN_FIXTURE)
    }),
  )
  renderScreen()

  const sunday = await day('Sunday')
  const row = sunday.getByText('Ven pongal').closest('li')!
  const swap = within(row).getByRole('button', { name: /swap/i })
  const lock = within(row).getByRole('button', { name: /^lock$/i })
  expect(swap).toBeEnabled()
  expect(lock).toBeEnabled()

  await userEvent.click(screen.getByRole('button', { name: /regenerate week/i }))

  expect(swap).toBeDisabled()
  expect(lock).toBeDisabled()
  release()
  await waitFor(() => expect(swap).toBeEnabled())
  expect(lock).toBeEnabled()
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
  // Awaited rather than a synchronous getByText: the region is named as soon as
  // `household` resolves, one render ahead of `cooking`'s own (sequential) fetch
  // settling, so its content is not necessarily there on the very first check.
  expect(await cooking.findByText('Idli with sambar')).toBeInTheDocument()
  expect(await cooking.findByText(/Sudev, Amma/)).toBeInTheDocument()
})

// --- descriptions (plan 9) ----------------------------------------------------------------

function stubWeek(week: WeekPlan) {
  server.use(http.get(apiUrl('/plan/week'), () => HttpResponse.json(week)))
}

/** A POST that answers only once the returned function is called. */
function holdPost(path: string, answer: WeekPlan): () => void {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.post(apiUrl(path), async () => {
      await held
      return HttpResponse.json(answer)
    }),
  )
  return () => release()
}

test('shows a dish’s description, and its cooking tip behind a disclosure', async () => {
  stubWeek(POLISHED_PLAN_FIXTURE)
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.getByText(PONGAL_TEXT.description)).toBeInTheDocument()
  const tip = sunday.getByText(PONGAL_TEXT.cooking_note)
  expect(tip.closest('details')).toContainElement(sunday.getByText('Cooking tip'))
  // A description with no tip shows no empty disclosure.
  const lunch = sunday.getByText('Rice with sambar').closest('li')!
  expect(within(lunch).getByText(SAMBAR_RICE_TEXT.description)).toBeInTheDocument()
  expect(within(lunch).queryByText('Cooking tip')).not.toBeInTheDocument()
})

test('a dish with no description shows neither a description nor a tip', async () => {
  renderScreen()

  const sunday = await day('Sunday')
  expect(sunday.queryByText('Cooking tip')).not.toBeInTheDocument()
  expect(sunday.queryByText(PONGAL_TEXT.description)).not.toBeInTheDocument()
})

// The spec's promise: polish never changes a dish, a portion or a rationale. On
// screen, that means the planner's own text renders exactly as it did without it.
test('the dish, its portion and the rationale render the same with a description', async () => {
  async function plannerText(week: WeekPlan): Promise<string[]> {
    stubWeek(week)
    const { unmount } = renderScreen()
    const sunday = await day('Sunday')
    const html = ['Ven pongal', '1.5 cup', 'Closes the morning protein gap with moong dal'].map(
      (text) => sunday.getByText(text).outerHTML,
    )
    unmount()
    return html
  }

  const plain = await plannerText(PLAN_FIXTURE)
  const polished = await plannerText(POLISHED_PLAN_FIXTURE)

  expect(polished).toStrictEqual(plain)
})

test.each([
  ['no key is saved', NO_KEY],
  ['the server has no keyring', { ...NO_KEY, available: false }],
  ['the saved key was refused', { ...KEY_SAVED, status: 'rejected' }],
] as const)('offers no descriptions when %s', async (_case, settings) => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(settings)))
  const { queryClient } = renderScreen()

  await day('Sunday')
  await waitFor(() =>
    expect(queryClient.getQueryState(['settings', 'llm'])?.status).toBe('success'),
  )
  expect(screen.queryByRole('button', { name: /add descriptions/i })).not.toBeInTheDocument()
})

test('adding descriptions sends the week and shows what came back', async () => {
  let posted: unknown = null
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json(POLISHED_PLAN_FIXTURE, {
        headers: { 'X-Dishes-Described': '2' },
      })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  const sunday = await day('Sunday')
  expect(await sunday.findByText(PONGAL_TEXT.description)).toBeInTheDocument()
  expect(posted).toStrictEqual({ start: weekStartIso() })
  // Two dishes got text, so there is nothing to explain.
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

// A refusal, an answer cut short, and text the server's check turned down all
// answer 200 with the week as it was. Only the count tells them from success.
test('a polish that described nothing says so, quietly', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), () =>
      HttpResponse.json(PLAN_FIXTURE, { headers: { 'X-Dishes-Described': '0' } }),
    ),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    /^Claude added no new descriptions this time\.$/,
  )
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled()
})

// Each answer replaces the whole week, so the one landing last would win.
test('descriptions wait while the week regenerates', async () => {
  const release = holdPost('/plan/week/regenerate', PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  renderScreen()

  const describe = await screen.findByRole('button', { name: 'Add descriptions' })
  expect(describe).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: /regenerate week/i }))

  expect(describe).toBeDisabled()
  release()
  await waitFor(() => expect(describe).toBeEnabled())
})

test('the week waits while descriptions are added', async () => {
  const release = holdPost('/plan/week/polish', POLISHED_PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(screen.getByRole('button', { name: 'Adding descriptions…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /regenerate week/i })).toBeDisabled()
  release()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /regenerate week/i })).toBeEnabled(),
  )
  expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled()
  // holdPost's answer has no X-Dishes-Described header. An unknown count says nothing.
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

// The lockout reads the mutation cache, not this screen's own observer, so it
// holds when the user leaves the Plan screen mid-polish and comes back.
test('the lockout holds when the screen is left and opened again mid-polish', async () => {
  const release = holdPost('/plan/week/polish', POLISHED_PLAN_FIXTURE)
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)))
  const { unmount, queryClient } = renderScreen()
  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))
  unmount()

  renderScreen(queryClient)

  expect(await screen.findByRole('button', { name: 'Adding descriptions…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /regenerate week/i })).toBeDisabled()
  release()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Add descriptions' })).toBeEnabled(),
  )
})

test('a failed polish says why in the server’s words, and leaves the plan alone', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(KEY_SAVED)),
    http.post(apiUrl('/plan/week/polish'), () =>
      HttpResponse.json(
        { detail: "Couldn't reach Anthropic. Your plan is unchanged." },
        { status: 502 },
      ),
    ),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    /^Couldn't reach Anthropic\. Your plan is unchanged\.$/,
  )
  expect((await day('Sunday')).getByText('Ven pongal')).toBeInTheDocument()
})

// The server marks a refused key, so the button goes, and the reason stays.
test('a key Anthropic refused takes the button away, and says where to fix it', async () => {
  let status: LlmSettings['status'] = 'ok'
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json({ ...KEY_SAVED, status })),
    http.post(apiUrl('/plan/week/polish'), () => {
      status = 'rejected'
      return HttpResponse.json(
        { detail: 'Anthropic refused your saved key. Replace it under AI descriptions.' },
        { status: 409 },
      )
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Add descriptions' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Anthropic refused your saved key. Replace it under AI descriptions.',
  )
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: /add descriptions/i })).not.toBeInTheDocument(),
  )
  expect(screen.getByRole('alert')).toBeInTheDocument()
})
