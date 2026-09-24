import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../lib/api'
import type { NewPushSubscription, PushDevices, PushPublicKey, PushUnsubscribe } from './types'

/**
 * Whether this browser can take meal reminders, and turning them on and off.
 *
 * - `unsupported`: no service worker, PushManager or Notification.
 * - `needs-install`: an iPhone or iPad outside the home screen. iOS delivers web
 *   push only to an installed app, and hides the APIs until then.
 * - `dev-worker`: the page is not under the production worker (`/sw.js`), which
 *   is the one with the push handler. In dev, MSW's worker owns the scope, or
 *   there is no worker at all.
 * - `ready`: a reminder can reach this browser.
 */
export type PushSupport = 'unsupported' | 'needs-install' | 'dev-worker' | 'ready'

/**
 * Where this browser stands, once it is `ready`.
 *
 * - `blocked`: notifications were denied, and asking again shows no prompt.
 * - `on`: permitted, and subscribed.
 * - `off`: neither, or permitted but no longer subscribed, as after signing out.
 */
export type DeviceState = 'blocked' | 'on' | 'off'

// The worker vite-plugin-pwa generates, which imports public/push-handlers.js.
const PRODUCTION_WORKER = '/sw.js'

function hasPushApis(): boolean {
  return (
    'serviceWorker' in navigator &&
    typeof window.PushManager !== 'undefined' &&
    typeof window.Notification !== 'undefined'
  )
}

function isAppleMobile(): boolean {
  const agent = navigator.userAgent
  // iPadOS asks for desktop sites, so an iPad says it is a Mac, but one with a
  // touch screen. Every browser on iOS is WebKit, so this is not only Safari.
  return (
    /iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && navigator.maxTouchPoints > 1)
  )
}

function isStandalone(): boolean {
  const displayMode =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(display-mode: standalone)').matches
  // Older iOS says it is on the home screen only through this non-standard flag.
  return displayMode || (navigator as Navigator & { standalone?: boolean }).standalone === true
}

export async function pushSupport(): Promise<PushSupport> {
  // Before the API check: Safari on an iPhone has none of them until it is
  // installed, and "unsupported" would hide the one thing that fixes it.
  if (isAppleMobile() && !isStandalone()) return 'needs-install'
  if (!hasPushApis()) return 'unsupported'
  try {
    // Not `.ready`, which never settles when no worker is registered at all, as
    // in dev with the mocks off. A worker still installing on a first visit
    // counts: subscribing waits for it.
    const registration = await navigator.serviceWorker.getRegistration()
    const worker = registration?.active ?? registration?.waiting ?? registration?.installing
    if (worker && new URL(worker.scriptURL).pathname.endsWith(PRODUCTION_WORKER)) return 'ready'
    return 'dev-worker'
  } catch {
    // A browser that refuses service workers here, such as a private window.
    return 'unsupported'
  }
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration()
  return (await registration?.pushManager.getSubscription()) ?? null
}

/**
 * Where this browser stands, resyncing the server on the way.
 *
 * A granted, live subscription reads as `on` from the browser alone, but the
 * browser cannot see whether the server still agrees: a session that expired,
 * another account signing in on this same phone, or the push service dropping
 * the subscription (a 404/410, or a rotated endpoint with no
 * `pushsubscriptionchange` handler here yet) all leave the server not
 * reminding this browser, or reminding someone else on it, while this browser
 * still reads `on`. So whenever the browser says `on`, this re-posts the
 * subscription; the server's upsert is idempotent, moving the endpoint to
 * whichever account is signed in here now and refreshing its timezone. The
 * re-post's own failure is swallowed: a background sync must not turn `on`
 * into a check-failed screen.
 */
export async function thisDevice(): Promise<DeviceState> {
  if (Notification.permission === 'denied') return 'blocked'
  const subscription = await currentSubscription()
  if (Notification.permission !== 'granted' || subscription === null) return 'off'
  await api
    .post<PushDevices>('/push/subscriptions', subscriptionBody(subscription))
    .catch(() => null)
  return 'on'
}

/** The server's VAPID public key, as the bytes `pushManager.subscribe` takes. */
function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4)
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(base64), (char) => char.charCodeAt(0))
}

/** The `POST /push/subscriptions` body for an already-subscribed browser. */
function subscriptionBody(subscription: PushSubscription): NewPushSubscription {
  const { keys } = subscription.toJSON()
  return {
    endpoint: subscription.endpoint,
    keys: { p256dh: keys?.p256dh ?? '', auth: keys?.auth ?? '' },
    // Reminder times are wall-clock, and this is the only thing that tells the
    // server which wall.
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }
}

/**
 * Ask for permission, subscribe this browser, and register it with the server.
 *
 * Call it straight from the tap. Resolves without subscribing when the prompt
 * is refused or dismissed, since that is the user's answer, not a failure.
 * Rejects with the `ApiError` when the server answers 503 (reminders are not set
 * up on it), or with whatever the browser or the server threw.
 */
export async function subscribeThisDevice(): Promise<void> {
  // First, before anything else is awaited. Safari shows the prompt only from
  // inside the tap that asked for it.
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return

  const { key } = await api.get<PushPublicKey>('/push/public-key')
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({
    // Every push shows a notification: Chrome requires the promise, and
    // push-handlers.js keeps it.
    userVisibleOnly: true,
    applicationServerKey: keyBytes(key),
  })

  try {
    await api.post<PushDevices>('/push/subscriptions', subscriptionBody(subscription))
  } catch (error) {
    // A browser subscription the server never stored would read as "on" here
    // and never be reminded. Undo it, so the button comes back.
    await subscription.unsubscribe().catch(() => false)
    throw error
  }
}

/**
 * Stop reminders on this browser: unsubscribe it, and tell the server.
 *
 * Never throws. Signing out calls it first, while the session still exists,
 * and a failure here must not keep anyone signed in.
 */
export async function unsubscribeThisDevice(): Promise<void> {
  let subscription: PushSubscription | null
  try {
    subscription = hasPushApis() ? await currentSubscription() : null
  } catch {
    return
  }
  if (subscription === null) return

  const body: PushUnsubscribe = { endpoint: subscription.endpoint }
  // Each half whatever happens to the other. The browser's own unsubscribe is
  // what stops the pushes: the push service then answers 410 to the server,
  // which forgets the device, so the DELETE is only the tidy way to get there.
  await subscription.unsubscribe().catch(() => false)
  await api.del('/push/subscriptions', body).catch(() => null)
}

export function usePushSupport() {
  return useQuery({ queryKey: ['push', 'support'], queryFn: pushSupport })
}

export function usePushKey() {
  return useQuery({
    queryKey: ['push', 'key'],
    queryFn: () => api.get<PushPublicKey>('/push/public-key'),
    // A 503 is an answer: this server sends no reminders. Retrying only delays it.
    retry: false,
  })
}

export function useThisDevice() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['push', 'device'], queryFn: thisDevice })
  useEffect(() => {
    // thisDevice() may just have re-posted this endpoint, which can change the
    // server's device count (moved from another account, or freshly caught up
    // after a drop). Sync the settings screen's count with it.
    if (query.data === 'on') {
      queryClient.invalidateQueries({ queryKey: ['settings', 'reminders'] })
    }
  }, [query.data, queryClient])
  return query
}

function useDeviceChange(change: () => Promise<void>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: change,
    // Settled rather than succeeded: a refused prompt resolves, and a failed
    // subscribe may still have changed the permission.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['push', 'device'] })
      queryClient.invalidateQueries({ queryKey: ['settings', 'reminders'] })
    },
  })
}

export function useTurnOnThisDevice() {
  return useDeviceChange(subscribeThisDevice)
}

export function useTurnOffThisDevice() {
  return useDeviceChange(unsubscribeThisDevice)
}
