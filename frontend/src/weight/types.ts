import type { Goal } from '../onboarding/types'

/**
 * CONTRACT for `GET /weight`, `POST /weight` and `DELETE /weight/{date}` — plan 7.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec: the
 * smoothed weight is null before the first weigh-in, the observed rate is its own
 * field, an adjustment says since when, and a weigh-in may carry a date.
 */

export interface WeighIn {
  date: string
  weight_kg: number
}

export interface NewWeighIn {
  weight_kg: number
  /** Defaults to the user's today on the server. A missed week can be filled in. */
  date?: string
}

export interface CalorieAdjustment {
  /**
   * Against the formula's figure. Bounded to ±10%, never below BMR, and a loss
   * target never below 1,200 kcal (women) or 1,500 kcal (men) unless maintenance
   * itself is lower.
   */
  delta_kcal: number
  since: string
  reason: string
}

export interface WeightTrend {
  /** Oldest first, the last year. The profile's weight is the newest of these. */
  weigh_ins: WeighIn[]
  /** Mean of the last three weigh-ins, so water weight does not cause thrash. */
  smoothed_kg: number | null
  goal: Goal
  /** What the goal's formula target implies, from its real deficit. */
  expected_kg_per_week: number
  /** Fitted over the last four weeks since the last step; null until three weigh-ins span two weeks. */
  observed_kg_per_week: number | null
  /** Today's energy target — the same figure the Today screen shows. */
  calorie_target_kcal: number
  adjustment: CalorieAdjustment | null
  /** One sentence on where the trend stands, or null. */
  note: string | null
}
