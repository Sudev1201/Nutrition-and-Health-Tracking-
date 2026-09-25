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

/**
 * `GET`, `PUT` and `DELETE /settings/llm` — plan 9.
 *
 * The key itself is write-only: it goes up once, in a `PUT` body, and nothing
 * sends it back. What comes back is its last four characters and whether
 * Anthropic accepted it.
 */
export type LlmKeyStatus = 'none' | 'ok' | 'rejected' | 'unreadable'

export interface LlmSettings {
  /** False when the server has no encryption keyring: the feature is off there. */
  available: boolean
  provider: 'anthropic' | null
  model: string | null
  /** The key's last four characters, never the key. */
  key_hint: string | null
  /**
   * `ok` once Anthropic accepted the key. `rejected` when it later refused it,
   * and `unreadable` when the server can no longer decrypt it: both need the key
   * entered again.
   */
  status: LlmKeyStatus
  /** The models this server offers, default first. */
  models: string[]
}

/**
 * `PUT /settings/llm` body. It answers `LlmSettings`, or 422 with a sentence in
 * `detail` when the key is malformed or Anthropic refuses it, or 503 when the
 * server cannot check it.
 */
export interface LlmKeyIn {
  api_key: string
  model: string
}

/** What each model is called on screen. Mirrors the backend's `providers.MODEL_LABELS`. */
export const MODEL_LABELS: Record<string, string> = {
  'claude-opus-5': 'Claude Opus 5',
  'claude-sonnet-5': 'Claude Sonnet 5',
  'claude-haiku-4-5': 'Claude Haiku 4.5',
}
