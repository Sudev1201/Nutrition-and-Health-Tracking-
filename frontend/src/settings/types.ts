import type { MealSlot } from '../log/types'

/**
 * PROPOSED CONTRACT for `GET/PATCH /settings/meal-times` and
 * `/settings/reminders` — implemented by plans 4 and 8.
 */
export interface MealTimeSetting {
  slot: MealSlot
  /** Usual weekday time, "HH:MM". */
  time: string
  /** Weekend variant — a Sunday breakfast rarely happens at 8am. */
  weekend_time: string | null
  /**
   * Whether to remind at this slot. The optional mid-morning snack should not
   * nag someone who rarely eats it.
   */
  reminder_on: boolean
}

export interface ReminderSettings {
  /** Whether the browser has granted notification permission. */
  push_granted: boolean
  slots: MealTimeSetting[]
}
