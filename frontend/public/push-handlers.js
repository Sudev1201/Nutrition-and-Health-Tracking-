/*
 * Meal reminders, inside the service worker.
 *
 * vite-plugin-pwa generates sw.js, and `workbox.importScripts` in vite.config.ts
 * loads this file into it. So this is plain JavaScript in the worker's global
 * scope: no imports, no bundling and no TypeScript. It is wrapped in a function
 * so that none of its names can collide with the generated worker's.
 *
 * The push payload is what the backend's WebPushChannel sends
 * (backend/app/reminders/channels.py):
 *   {"title": "Lunch", "body": "Nothing logged for lunch yet. Tap to log it.",
 *    "url": "/log?slot=lunch", "tag": "lunch-2026-08-17"}
 */
(() => {
  const FALLBACK = {
    title: 'Nutrient Tracker',
    body: 'Time to log your meal.',
    url: '/log',
    tag: undefined,
  }

  function readPayload(event) {
    if (!event.data) return FALLBACK
    try {
      const sent = event.data.json()
      const text = (value, otherwise) => (typeof value === 'string' ? value : otherwise)
      return {
        title: text(sent.title, FALLBACK.title),
        body: text(sent.body, FALLBACK.body),
        url: text(sent.url, FALLBACK.url),
        tag: text(sent.tag, FALLBACK.tag),
      }
    } catch {
      return FALLBACK
    }
  }

  /** The URL to open, on this app's own origin whatever the payload says. */
  function sameOrigin(raw) {
    const origin = self.location.origin
    try {
      const url = new URL(raw, origin)
      if (url.origin === origin) return url.href
    } catch {
      // Not a URL at all. The Log screen is the safe place to land.
    }
    return new URL(FALLBACK.url, origin).href
  }

  self.addEventListener('push', (event) => {
    // Always show what arrived, even a payload this file cannot read. A push that
    // shows nothing gets a generic notification on Chrome, and Safari can revoke
    // the subscription for it. Whether to send at all is the server's decision.
    const payload = readPayload(event)
    const options = { body: payload.body, icon: '/icon-192.png', data: { url: payload.url } }
    // One notification per slot and day: a second push with the same tag
    // replaces the first rather than stacking beside it.
    if (payload.tag !== undefined) options.tag = payload.tag
    event.waitUntil(self.registration.showNotification(payload.title, options))
  })

  async function openAt(url) {
    // Only windows this worker controls: navigate() refuses any other.
    const windows = await self.clients.matchAll({ type: 'window' })
    for (const client of windows) {
      try {
        await client.focus()
        await client.navigate(url)
        return
      } catch {
        // A window that cannot be focused or navigated. Try the next one.
      }
    }
    await self.clients.openWindow(url)
  }

  self.addEventListener('notificationclick', (event) => {
    event.notification.close()
    const url = sameOrigin(event.notification.data?.url ?? FALLBACK.url)
    event.waitUntil(openAt(url))
  })
})()
