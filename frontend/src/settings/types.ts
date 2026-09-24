import type { MealSlot } from '../log/types'

/**
 * CONTRACT for `GET /settings/reminders`, `PATCH /settings/reminders` and the
 * `/push` routes — plan 8.
 *
 * Amended from the plan 2.5 proposal. `push_granted` is gone: whether a browser
 * may show notifications is a fact about that one browser, which it reads for
 * itself (`usePush.ts`). In its place is the number of this user's subscribed
 * devices. The times themselves are the profile's, and are edited there.
 */
export interface MealTimeSetting {
  slot: MealSlot
  /** Usual weekday time, "HH:MM". */
  time: string
  /** Saturday and Sunday, when it differs — a Sunday breakfast rarely happens at 8am. */
  weekend_time: string | null
  /**
   * Whether to remind at this slot. The optional mid-morning snack is off by
   * default, so it does not nag someone who rarely eats it.
   */
  reminder_on: boolean
}

export interface ReminderSettings {
  /** The slots enabled in the profile, in meal order. A switched-off snack is left out. */
  slots: MealTimeSetting[]
  /** This user's browsers subscribed to push, on every device they use. */
  devices: number
}

/** `PATCH /settings/reminders` body. It answers with the whole `ReminderSettings`. */
export interface ReminderChange {
  slot: MealSlot
  reminder_on: boolean
}

/**
 * `GET /push/public-key`. Answers 503 "Reminders are not set up on this server"
 * until the server has its VAPID key pair.
 */
export interface PushPublicKey {
  key: string
}

/**
 * `POST /push/subscriptions` body: the browser's subscription, and its IANA
 * timezone, which is the only thing that sets the user's. It answers 201
 * `PushDevices`.
 */
export interface NewPushSubscription {
  endpoint: string
  keys: { p256dh: string; auth: string }
  timezone?: string
}

export interface PushDevices {
  devices: number
}

/**
 * `DELETE /push/subscriptions` body. It answers 204, or 404 when the endpoint is
 * not this user's.
 */
export interface PushUnsubscribe {
  endpoint: string
}
