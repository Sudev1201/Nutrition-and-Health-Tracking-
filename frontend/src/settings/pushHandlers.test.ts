import { expect, test, vi } from 'vitest'
import source from '../../public/push-handlers.js?raw'

/*
 * public/push-handlers.js runs inside the service worker, which jsdom does not
 * have. It touches nothing but `self`, so it is run here against a stand-in for
 * the worker's global scope, and its events are dispatched by hand.
 */

const ORIGIN = 'https://nutrients.example'

// What Task 11's WebPushChannel sends for lunch on 17 August.
const LUNCH = {
  title: 'Lunch',
  body: 'Nothing logged for lunch yet. Tap to log it.',
  url: '/log?slot=lunch',
  tag: 'lunch-2026-08-17',
}

/** A window of this app that the worker controls. */
function windowClient() {
  return {
    url: `${ORIGIN}/`,
    focus: vi.fn(async () => undefined),
    navigate: vi.fn(async (_url: string) => undefined),
  }
}

function worker(windows: ReturnType<typeof windowClient>[] = []) {
  const listeners = new Map<string, (event: object) => void>()
  const scope = {
    location: new URL(`${ORIGIN}/sw.js`),
    registration: { showNotification: vi.fn(async (_title: string, _options: object) => {}) },
    clients: {
      matchAll: vi.fn(async (_options: object) => windows),
      openWindow: vi.fn(async (_url: string) => null),
    },
    addEventListener: (type: string, listener: (event: object) => void) => {
      listeners.set(type, listener)
    },
  }
  new Function('self', source)(scope)

  /** Dispatch one event, and wait for everything it asked the worker to wait for. */
  async function dispatch(type: string, event: object) {
    const pending: Promise<unknown>[] = []
    listeners.get(type)?.({ ...event, waitUntil: (work: Promise<unknown>) => pending.push(work) })
    await Promise.all(pending)
  }

  return { scope, dispatch }
}

function push(payload: unknown) {
  return { data: { json: () => payload } }
}

function click(url: unknown) {
  return { notification: { data: { url }, close: vi.fn() } }
}

test('a push shows exactly what the server sent', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', push(LUNCH))

  expect(scope.registration.showNotification).toHaveBeenCalledWith('Lunch', {
    body: 'Nothing logged for lunch yet. Tap to log it.',
    tag: 'lunch-2026-08-17',
    icon: '/icon-192.png',
    data: { url: '/log?slot=lunch' },
  })
})

// A push that shows nothing gets a generic notification on Chrome, and Safari
// can revoke the subscription for it.
test('a push it cannot read still shows a notification', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', {
    data: {
      json: () => {
        throw new SyntaxError('Unexpected token')
      },
    },
  })

  expect(scope.registration.showNotification).toHaveBeenCalledWith('Nutrient Tracker', {
    body: 'Time to log your meal.',
    icon: '/icon-192.png',
    data: { url: '/log' },
  })
})

test('a push with no payload still shows a notification', async () => {
  const { scope, dispatch } = worker()

  await dispatch('push', { data: null })

  expect(scope.registration.showNotification).toHaveBeenCalledWith(
    'Nutrient Tracker',
    expect.objectContaining({ body: 'Time to log your meal.' }),
  )
})

test('a tap brings an open window to the slot’s logging screen', async () => {
  const open = windowClient()
  const { scope, dispatch } = worker([open])
  const event = click('/log?slot=lunch')

  await dispatch('notificationclick', event)

  expect(event.notification.close).toHaveBeenCalledOnce()
  expect(scope.clients.matchAll).toHaveBeenCalledWith({ type: 'window' })
  expect(open.focus).toHaveBeenCalledOnce()
  expect(open.navigate).toHaveBeenCalledWith(`${ORIGIN}/log?slot=lunch`)
  expect(scope.clients.openWindow).not.toHaveBeenCalled()
})

test('with no window open, a tap opens one at the slot', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', click('/log?slot=dinner'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log?slot=dinner`)
})

test('a window that cannot be navigated gives way to a new one', async () => {
  const stuck = windowClient()
  stuck.navigate.mockRejectedValue(new TypeError('This service worker is not the client’s'))
  const { scope, dispatch } = worker([stuck])

  await dispatch('notificationclick', click('/log?slot=lunch'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log?slot=lunch`)
})

// The payload comes only from this app's server, but a notification is never
// a way off the app.
test('a link to another site opens the Log screen instead', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', click('https://elsewhere.example/log'))

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log`)
})

test('a notification with no link opens the Log screen', async () => {
  const { scope, dispatch } = worker()

  await dispatch('notificationclick', { notification: { data: null, close: vi.fn() } })

  expect(scope.clients.openWindow).toHaveBeenCalledWith(`${ORIGIN}/log`)
})
