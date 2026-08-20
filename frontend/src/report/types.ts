import type { NutrientUnit } from '../lib/format'
import type { NutrientKind } from '../lib/status'

/**
 * PROPOSED CONTRACT for `GET /reports/week?start=` — implemented by plan 8.
 */

export interface ReportDay {
  date: string
  weekday: string
  energy_kcal: number
  target_kcal: number
}

export interface ReportNutrient {
  code: string
  display_name: string
  unit: NutrientUnit
  kind: NutrientKind
  ear: number | null
  tul: number | null
  /** Sum of the seven days' effective targets. */
  target_total: number
  consumed_total: number
  /** Days out of 7 the nutrient reached its target. */
  days_met: number
}

/**
 * A shortfall the compensation engine could not make up, because carrying it
 * would have breached a cap. The spec requires the report to show these honestly
 * rather than quietly dropping them.
 */
export interface UncompensatedGap {
  code: string
  display_name: string
  unit: NutrientUnit
  amount: number
  reason: string
}

export interface WeeklyReport {
  start_date: string
  end_date: string
  /** Meal slots logged out of the week's total. */
  slots_logged: number
  slots_total: number
  /** Energy from weighed entries vs from estimated ones. */
  measured_kcal: number
  estimated_kcal: number
  days: ReportDay[]
  nutrients: ReportNutrient[]
  uncompensated: UncompensatedGap[]
  suggestions: string[]
}
