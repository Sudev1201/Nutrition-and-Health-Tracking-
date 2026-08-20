/** PROPOSED CONTRACT for `GET/POST /weight` — implemented by plan 7. */

export interface WeighIn {
  date: string
  weight_kg: number
}

export interface WeightTrend {
  weigh_ins: WeighIn[]
  /** Smoothed over the last 2-3 weigh-ins so water weight does not cause thrash. */
  smoothed_kg: number
  goal: 'lose' | 'maintain' | 'gain'
  /** The trajectory the goal implies, e.g. -0.5 kg/week. */
  expected_kg_per_week: number
  calorie_target_kcal: number
  /**
   * Set when sustained drift moved the calorie target. The step is bounded to
   * ±10% and clamped so it never falls below BMR.
   */
  adjustment: {
    delta_kcal: number
    reason: string
  } | null
}
