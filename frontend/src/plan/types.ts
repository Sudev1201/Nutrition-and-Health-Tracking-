import type { MealSlot } from '../log/types'

/**
 * PROPOSED CONTRACT for `GET /plan/week?start=` and the swap/lock/regenerate
 * endpoints — implemented by plan 6.
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
