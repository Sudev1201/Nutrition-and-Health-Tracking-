import type { MealSlot } from '../log/types'

/**
 * CONTRACT for `GET /plan/week?start=` and the swap, lock and regenerate
 * endpoints, built in plan 6, and for `POST /plan/week/polish`, built in plan 9.
 * Each of them answers the whole `WeekPlan`.
 */

export interface PlanItem {
  id: string
  slot: MealSlot
  dish_id: string
  dish_name: string
  portion: string
  /** A locked item is preserved when the day or week is regenerated. */
  locked: boolean
  /** Why the planner chose this — shown so the plan is not a black box. */
  rationale: string | null
  /**
   * One sentence on what the dish is, written by Claude once the user asks for
   * descriptions with their own Anthropic key (plan 9). Null until then, and for
   * a dish the model declined or whose text failed the server's check. It sits
   * beside the planner's fields and never replaces one: a description changes no
   * dish, portion, rationale or number.
   */
  description: string | null
  /** A tip for cooking the same dish at home, or null. Only ever set with a description. */
  cooking_note: string | null
}

export interface PlanDay {
  date: string
  /** Sunday-to-Saturday weekday name. */
  weekday: string
  /**
   * A hard constraint from the user's observance rules. On these days egg counts
   * as non-vegetarian and is excluded along with meat and fish.
   */
  vegetarian: boolean
  /** Why the day is vegetarian, e.g. "Purattasi" or "your Friday rule". */
  vegetarian_reason: string | null
  items: PlanItem[]
}

export interface WeekPlan {
  start_date: string
  days: PlanDay[]
}

/** `GET /plan/cooking?date=` — where household members' plans coincide. */
export interface CookingOverlap {
  slot: MealSlot
  dish_name: string
  /** Names of the members whose plan has this dish in this slot. */
  members: string[]
}

export interface CookingView {
  date: string
  overlaps: CookingOverlap[]
}
