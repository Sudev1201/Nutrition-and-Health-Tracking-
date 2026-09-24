import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { REMINDERS_FIXTURE } from '../mocks/fixtures/more'
import {
  ENDPOINT,
  IPHONE_SAFARI,
  MOCK_WORKER,
  installPush,
  pretendToBe,
  uninstallPush,
} from '../mocks/pushApis'
import { server } from '../mocks/server'
import type { SavedProfile } from '../onboarding/useProfile'
import { RemindersScreen } from './RemindersScreen'
import type { ReminderSettings } from './types'

const TURN_ON = { name: 'Turn on reminders on this device' }

let devices = 0

beforeEach(() => {
  devices = 0
  server.use(
    http.get(apiUrl('/settings/reminders'), () =>
      HttpResponse.json<ReminderSettings>({ ...REMINDERS_FIXTURE, devices }),
    ),
  )
})

afterEach(() => uninstallPush())

function serveKey() {
  server.use(http.get(apiUrl('/push/public-key'), () => HttpResponse.json({ key: 'AQID-_8' })))
}

/** The PATCH answers as the server does after dinner's switch: the whole settings. */
function serveDinnerOff(patched: (body: unknown) => void = () => {}) {
  server.use(
    http.patch(apiUrl('/settings/reminders'), async ({ request }) => {
      patched(await request.json())
      return HttpResponse.json<ReminderSettings>({
        ...REMINDERS_FIXTURE,
        slots: REMINDERS_FIXTURE.slots.map((slot) =>
          slot.slot === 'dinner' ? { ...slot, reminder_on: false } : slot,
        ),
      })
    }),
  )
}

function newQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderScreen(queryClient = newQueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RemindersScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function cachedDinner(queryClient: QueryClient) {
  return queryClient
    .getQueryData<SavedProfile>(['profile'])
    ?.meal_times.find((item) => item.slot === 'dinner')
}

// --- the slots --------------------------------------------------------------------------

test('lists every meal slot with its usual time', async () => {
  renderScreen()

  expect(await screen.findByRole('switch', { name: /breakfast · 08:00/i })).toBeInTheDocument()
  expect(await screen.findByRole('switch', { name: /dinner · 20:30/i })).toBeInTheDocument()
  expect(screen.getByText('Weekends at 09:30')).toBeInTheDocument()
})

// The optional mid-morning snack must not nag someone who rarely eats it.
test('shows the optional snack reminder as off', async () => {
  renderScreen()

  expect(
    await screen.findByRole('switch', { name: /mid-morning snack/i }),
  ).not.toBeChecked()
})

test('turning a slot’s reminder off sends just that slot', async () => {
  const patched = vi.fn()
  serveDinnerOff(patched)
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  await userEvent.click(dinner)

  await waitFor(() =>
    expect(patched).toHaveBeenCalledWith({ slot: 'dinner', reminder_on: false }),
  )
  // The answer is the saved state, and the switch shows it.
  await waitFor(() => expect(dinner).not.toBeChecked())
})

test('a reminder that could not be changed says so, and stays as it was', async () => {
  server.use(
    http.patch(apiUrl('/settings/reminders'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  await userEvent.click(dinner)

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be changed/)
  expect(dinner).toBeChecked()
})

// The answer replaces every switch, so an earlier answer landing late would undo a later one.
test('the switches wait for the last change before taking another', async () => {
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.patch(apiUrl('/settings/reminders'), async () => {
      await held
      return HttpResponse.json<ReminderSettings>(REMINDERS_FIXTURE)
    }),
  )
  renderScreen()

  const dinner = await screen.findByRole('switch', { name: /dinner/i })
  const breakfast = screen.getByRole('switch', { name: /breakfast/i })
  await userEvent.click(dinner)

  await waitFor(() => expect(breakfast).toBeDisabled())
  release()
  await waitFor(() => expect(breakfast).toBeEnabled())
})

// The profile form sends every slot's reminder back with a save, from the profile
// it last read. Left stale, that copy would switch this reminder back on.
test('a switch changed here is what the profile form sends next', async () => {
  serveDinnerOff()
  const queryClient = newQueryClient()
  queryClient.setQueryData(['profile'], {
    meal_times: REMINDERS_FIXTURE.slots.map((slot) => ({ ...slot, is_enabled: true })),
  })
  renderScreen(queryClient)

  await userEvent.click(await screen.findByRole('switch', { name: /dinner/i }))

  await waitFor(() => expect(cachedDinner(queryClient)?.reminder_on).toBe(false))
  expect(queryClient.getQueryData<SavedProfile>(['profile'])?.meal_times).toHaveLength(5)
})

test('a profile saved before meal times existed gains the row the switch created', async () => {
  serveDinnerOff()
  const queryClient = newQueryClient()
  queryClient.setQueryData(['profile'], { meal_times: [] })
  renderScreen(queryClient)

  await userEvent.click(await screen.findByRole('switch', { name: /dinner/i }))

  await waitFor(() =>
    expect(cachedDinner(queryClient)).toEqual({
      slot: 'dinner',
      time: '20:30',
      weekend_time: null,
      reminder_on: false,
      is_enabled: true,
    }),
  )
})

test('sends a user with no profile to set one up rather than showing an error', async () => {
  server.use(
    http.get(apiUrl('/settings/reminders'), () => new HttpResponse('no profile', { status: 404 })),
  )
  renderScreen()

  expect(await screen.findByRole('link', { name: 'Set up your profile' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// --- this device ------------------------------------------------------------------------

// iOS only delivers web push to a PWA installed on the home screen, which is a
// real constraint the user has to be told about rather than left to discover.
test('explains the iPhone install requirement before offering anything', async () => {
  pretendToBe(IPHONE_SAFARI)
  renderScreen()

  expect(await screen.findByText(/add this app to your home screen/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('a browser without push is told so, and offered nothing', async () => {
  renderScreen()

  expect(await screen.findByText('This browser can’t show reminders')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

// In dev, MSW's worker owns the page and has no push handler.
test('a page the mock worker controls offers nothing', async () => {
  installPush({ worker: MOCK_WORKER })
  renderScreen()

  expect(
    await screen.findByText('Reminders can’t be turned on from this page'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('says so when the server is not set up to send reminders', async () => {
  installPush()
  server.use(
    http.get(
      apiUrl('/push/public-key'),
      () => new HttpResponse('Reminders are not set up on this server', { status: 503 }),
    ),
  )
  renderScreen()

  expect(await screen.findByText('Reminders are not set up on this server')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('does not offer a prompt the browser has already refused', async () => {
  installPush({ permission: 'denied' })
  serveKey()
  renderScreen()

  expect(await screen.findByText('Notifications are blocked for this app')).toBeInTheDocument()
  expect(screen.queryByRole('button', TURN_ON)).not.toBeInTheDocument()
})

test('turns reminders on for this device', async () => {
  const push = installPush()
  serveKey()
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      posted = await request.json()
      devices = 1
      return HttpResponse.json({ devices }, { status: 201 })
    }),
  )
  renderScreen()

  expect(
    await screen.findByText('No device has reminders turned on for your account yet.'),
  ).toBeInTheDocument()
  await userEvent.click(await screen.findByRole('button', TURN_ON))

  expect(await screen.findByText('Reminders are on for this device')).toBeInTheDocument()
  expect(
    await screen.findByText('Reminders go to 1 device on your account.'),
  ).toBeInTheDocument()
  expect(push.notification.requestPermission).toHaveBeenCalledOnce()
  expect(posted).toMatchObject({ endpoint: ENDPOINT })
})

test('a device with reminders on can turn them off', async () => {
  installPush({ permission: 'granted', subscribed: true })
  serveKey()
  devices = 1
  let forgotten: unknown = null
  server.use(
    // A device reading "on" re-posts itself to catch the server up; this one
    // already agrees, so the re-post changes nothing.
    http.post(apiUrl('/push/subscriptions'), () => HttpResponse.json({ devices }, { status: 201 })),
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      forgotten = await request.json()
      devices = 0
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Turn off on this device' }))

  expect(await screen.findByRole('button', TURN_ON)).toBeInTheDocument()
  expect(forgotten).toEqual({ endpoint: ENDPOINT })
})

// The plan's own decision -- "a subscription re-posted by another account moves
// to that account, so a shared phone reminds only its current user" -- has to
// be reachable just by opening the screen, not only by tapping Turn off then
// Turn on. A session that expired, or a different account signing in on this
// phone, leaves the browser subscribed while the server's count is still 0.
test('a subscribed browser catches the server up, and the count follows', async () => {
  installPush({ permission: 'granted', subscribed: true })
  serveKey()
  devices = 0
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      posted = await request.json()
      devices = 1
      return HttpResponse.json({ devices }, { status: 201 })
    }),
  )

  renderScreen()

  expect(await screen.findByText('Reminders are on for this device')).toBeInTheDocument()
  expect(
    await screen.findByText('Reminders go to 1 device on your account.'),
  ).toBeInTheDocument()
  expect(posted).toMatchObject({ endpoint: ENDPOINT })
})
