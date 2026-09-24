import { http, HttpResponse } from 'msw'
import { afterEach, expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import {
  AUTH,
  ENDPOINT,
  IPAD_SAFARI,
  IPHONE_SAFARI,
  MOCK_WORKER,
  P256DH,
  installPush,
  pretendToBe,
  uninstallPush,
} from '../mocks/pushApis'
import { server } from '../mocks/server'
import { pushSupport, subscribeThisDevice, thisDevice, unsubscribeThisDevice } from './usePush'

// Base64url, unpadded, with both of the characters plain base64 spells differently.
const KEY = 'AQID-_8'
const KEY_BYTES = [1, 2, 3, 251, 255]

afterEach(() => uninstallPush())

function serveKey(events: string[] = []) {
  server.use(
    http.get(apiUrl('/push/public-key'), () => {
      events.push('key')
      return HttpResponse.json({ key: KEY })
    }),
  )
}

// --- what this browser can do ---------------------------------------------------------

test('a browser without push cannot take reminders', async () => {
  expect(await pushSupport()).toBe('unsupported')
})

test('a browser missing only notifications cannot take reminders', async () => {
  installPush()
  vi.stubGlobal('Notification', undefined)

  expect(await pushSupport()).toBe('unsupported')
})

// iOS delivers web push only to an app on the home screen, and until then Safari
// has none of the APIs. Reading that as "unsupported" would hide the one fix.
test('Safari on an iPhone must add the app to the home screen first', async () => {
  pretendToBe(IPHONE_SAFARI)

  expect(await pushSupport()).toBe('needs-install')
})

test('an iPad that says it is a Mac is still an iPad', async () => {
  pretendToBe(IPAD_SAFARI, { maxTouchPoints: 5 })

  expect(await pushSupport()).toBe('needs-install')
})

test('a Mac is not an iPad', async () => {
  pretendToBe(IPAD_SAFARI, { maxTouchPoints: 0 })
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('the app on an iPhone home screen can take reminders', async () => {
  pretendToBe(IPHONE_SAFARI)
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(display-mode: standalone)',
  }))
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('older iOS says it is on the home screen through navigator.standalone', async () => {
  pretendToBe(IPHONE_SAFARI, { standalone: true })
  installPush()

  expect(await pushSupport()).toBe('ready')
})

// In dev, MSW's worker owns the scope and has no push handler.
test('a page the mock worker controls cannot subscribe', async () => {
  installPush({ worker: MOCK_WORKER })

  expect(await pushSupport()).toBe('dev-worker')
})

// `ready` never settles here, so waiting on it would hang the screen.
test('a page with no worker at all is told so, without waiting for one', async () => {
  installPush({ worker: null })

  expect(await pushSupport()).toBe('dev-worker')
})

test('the production worker can take reminders', async () => {
  installPush()

  expect(await pushSupport()).toBe('ready')
})

test('the production worker counts while it is still installing', async () => {
  installPush({ installing: true })

  expect(await pushSupport()).toBe('ready')
})

test('a browser that refuses to look up its worker cannot take reminders', async () => {
  const push = installPush()
  push.container.getRegistration.mockRejectedValue(new DOMException('denied', 'SecurityError'))

  expect(await pushSupport()).toBe('unsupported')
})

// --- where this device stands ---------------------------------------------------------

test('a device that denied notifications is blocked', async () => {
  installPush({ permission: 'denied' })

  expect(await thisDevice()).toBe('blocked')
})

test('a permitted, subscribed device is on', async () => {
  installPush({ permission: 'granted', subscribed: true })
  server.use(
    http.post(apiUrl('/push/subscriptions'), () =>
      HttpResponse.json({ devices: 1 }, { status: 201 }),
    ),
  )

  expect(await thisDevice()).toBe('on')
})

// After signing out, the permission stays but the subscription is gone. Reading
// that as "on" would leave the next person with no way to turn reminders on.
test('a permitted device with no subscription is off', async () => {
  installPush({ permission: 'granted' })

  expect(await thisDevice()).toBe('off')
})

// The browser cannot see whether the server still agrees with it: a session
// that expired, another account signing in on this same phone, or a dropped
// subscription all leave the browser reading "on" while the server does not
// remind it, or reminds someone else. The upsert is idempotent, so this is
// how a shared phone's reminders end up on its current user without a manual
// turn-off/turn-on.
test('a device reading "on" re-posts its subscription, in case the server disagrees', async () => {
  installPush({ permission: 'granted', subscribed: true })
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      posted = await request.json()
      return HttpResponse.json({ devices: 1 }, { status: 201 })
    }),
  )

  expect(await thisDevice()).toBe('on')

  expect(posted).toEqual({
    endpoint: ENDPOINT,
    keys: { p256dh: P256DH, auth: AUTH },
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  })
})

test('a device still reads "on" when the server cannot take the re-post', async () => {
  installPush({ permission: 'granted', subscribed: true })
  server.use(
    http.post(apiUrl('/push/subscriptions'), () => new HttpResponse('boom', { status: 500 })),
  )

  expect(await thisDevice()).toBe('on')
})

// --- turning reminders on -------------------------------------------------------------

test('asks first, then subscribes with the server’s key, and registers the device', async () => {
  const events: string[] = []
  const push = installPush()
  push.notification.requestPermission.mockImplementation(async () => {
    events.push('permission')
    push.notification.permission = 'granted'
    return 'granted'
  })
  push.pushManager.subscribe.mockImplementation(async () => {
    events.push('subscribe')
    return push.subscription
  })
  serveKey(events)
  let posted: unknown = null
  server.use(
    http.post(apiUrl('/push/subscriptions'), async ({ request }) => {
      events.push('register')
      posted = await request.json()
      return HttpResponse.json({ devices: 1 }, { status: 201 })
    }),
  )

  await subscribeThisDevice()

  // The prompt comes first: Safari shows it only from inside the tap.
  expect(events).toEqual(['permission', 'key', 'subscribe', 'register'])
  const [options] = push.pushManager.subscribe.mock.calls[0]
  expect(options.userVisibleOnly).toBe(true)
  expect(Array.from(options.applicationServerKey as Uint8Array)).toEqual(KEY_BYTES)
  expect(posted).toEqual({
    endpoint: ENDPOINT,
    keys: { p256dh: P256DH, auth: AUTH },
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  })
})

test('a refused prompt subscribes nothing, and is not an error', async () => {
  const events: string[] = []
  const push = installPush({ answer: 'denied' })
  serveKey(events)

  await expect(subscribeThisDevice()).resolves.toBeUndefined()

  expect(events).toEqual([])
  expect(push.pushManager.subscribe).not.toHaveBeenCalled()
})

test('a server without push keys says so, and nothing is subscribed', async () => {
  const push = installPush()
  server.use(
    http.get(
      apiUrl('/push/public-key'),
      () => new HttpResponse('Reminders are not set up on this server', { status: 503 }),
    ),
  )

  await expect(subscribeThisDevice()).rejects.toMatchObject({ status: 503 })
  expect(push.pushManager.subscribe).not.toHaveBeenCalled()
})

// Left subscribed, the browser would read as "on" while the server never reminds it.
test('a device the server could not store is not left subscribed', async () => {
  const push = installPush()
  serveKey()
  server.use(
    http.post(apiUrl('/push/subscriptions'), () => new HttpResponse('boom', { status: 500 })),
  )

  await expect(subscribeThisDevice()).rejects.toMatchObject({ status: 500 })
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(await thisDevice()).toBe('off')
})

// --- turning reminders off ------------------------------------------------------------

test('turning off unsubscribes the browser and forgets the device on the server', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  let forgotten: unknown = null
  server.use(
    http.delete(apiUrl('/push/subscriptions'), async ({ request }) => {
      forgotten = await request.json()
      return new HttpResponse(null, { status: 204 })
    }),
  )

  await unsubscribeThisDevice()

  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
  expect(forgotten).toEqual({ endpoint: ENDPOINT })
})

test('with nothing subscribed, nothing is sent', async () => {
  installPush({ permission: 'granted' })
  const deleted = vi.fn()
  server.use(
    http.delete(apiUrl('/push/subscriptions'), () => {
      deleted()
      return new HttpResponse(null, { status: 204 })
    }),
  )

  await unsubscribeThisDevice()

  expect(deleted).not.toHaveBeenCalled()
})

test('a server that cannot forget the device still leaves the browser unsubscribed', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  server.use(
    http.delete(apiUrl('/push/subscriptions'), () => new HttpResponse('boom', { status: 500 })),
  )

  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
  expect(push.subscription.unsubscribe).toHaveBeenCalledOnce()
})

test('turning off never throws, whatever the browser does', async () => {
  const push = installPush({ permission: 'granted', subscribed: true })
  push.container.getRegistration.mockRejectedValue(new DOMException('denied', 'SecurityError'))

  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
})

test('turning off in a browser without push does nothing', async () => {
  await expect(unsubscribeThisDevice()).resolves.toBeUndefined()
})
