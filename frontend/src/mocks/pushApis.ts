import { vi } from 'vitest'

/**
 * Stand-ins for the browser's push APIs, which jsdom does not have: the service
 * worker container, PushManager and Notification. Test support only; nothing in
 * the app imports this file.
 *
 * `installPush` puts them in place for one test, and `pretendToBe` changes what
 * the browser says it is. Call `uninstallPush` from `afterEach` to take both away
 * again, so the next test starts as jsdom does: a browser with no push at all.
 */

export const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/this-device'
export const P256DH = 'B' + 'p'.repeat(86)
export const AUTH = 'a'.repeat(22)

export const PRODUCTION_WORKER = 'http://localhost:3000/sw.js'
export const MOCK_WORKER = 'http://localhost:3000/mockServiceWorker.js'

export const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
/** iPadOS asks for desktop sites, so its Safari says it is a Mac. */
export const IPAD_SAFARI =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/18.5 Safari/605.1.15'

interface PushOptions {
  /** The script of the page's worker, or null when no worker is registered at all. */
  worker?: string | null
  /** The worker is still installing, as on a first visit. */
  installing?: boolean
  permission?: NotificationPermission
  /** What the permission prompt answers. */
  answer?: NotificationPermission
  /** This browser is already subscribed. */
  subscribed?: boolean
}

function fakeSubscription(onUnsubscribe: () => void) {
  return {
    endpoint: ENDPOINT,
    toJSON: (): PushSubscriptionJSON => ({
      endpoint: ENDPOINT,
      expirationTime: null,
      keys: { p256dh: P256DH, auth: AUTH },
    }),
    unsubscribe: vi.fn(async () => {
      onUnsubscribe()
      return true
    }),
  }
}

export function installPush({
  worker = PRODUCTION_WORKER,
  installing = false,
  permission = 'default',
  answer = 'granted',
  subscribed = false,
}: PushOptions = {}) {
  let current: ReturnType<typeof fakeSubscription> | null = null
  const subscription = fakeSubscription(() => {
    current = null
  })
  if (subscribed) current = subscription

  const pushManager = {
    getSubscription: vi.fn(async () => current),
    subscribe: vi.fn(async (_options: PushSubscriptionOptionsInit) => {
      current = subscription
      return subscription
    }),
  }
  const script = worker === null ? null : { scriptURL: worker }
  const registration =
    script === null
      ? undefined
      : {
          active: installing ? null : script,
          waiting: null,
          installing: installing ? script : null,
          pushManager,
        }
  const container = {
    getRegistration: vi.fn(async () => registration),
    // With no worker it never settles, as in a real browser.
    ready: registration === undefined ? new Promise(() => {}) : Promise.resolve(registration),
  }
  Object.defineProperty(navigator, 'serviceWorker', { value: container, configurable: true })

  const notification = {
    permission,
    requestPermission: vi.fn(async () => {
      notification.permission = answer
      return answer
    }),
  }
  vi.stubGlobal('Notification', notification)
  vi.stubGlobal('PushManager', class PushManager {})

  return { container, pushManager, subscription, notification }
}

export function pretendToBe(
  userAgent: string,
  { standalone, maxTouchPoints }: { standalone?: boolean; maxTouchPoints?: number } = {},
) {
  Object.defineProperty(navigator, 'userAgent', { value: userAgent, configurable: true })
  if (standalone !== undefined) {
    Object.defineProperty(navigator, 'standalone', { value: standalone, configurable: true })
  }
  if (maxTouchPoints !== undefined) {
    Object.defineProperty(navigator, 'maxTouchPoints', {
      value: maxTouchPoints,
      configurable: true,
    })
  }
}

export function uninstallPush() {
  // Own properties only: jsdom's own userAgent, on the prototype, shows through again.
  for (const name of ['serviceWorker', 'userAgent', 'standalone', 'maxTouchPoints']) {
    Reflect.deleteProperty(navigator, name)
  }
  vi.unstubAllGlobals()
}
