import type { NutrientUnit } from '../lib/format'
import type { NutrientKind } from '../lib/status'

/**
 * CONTRACT for `GET /targets/today?date=`. Implemented by the backend's
 * `app/targets/router.py`.
 */
export interface NutrientProgress {
  /** Matches `nutrients.code` in the backend. */
  code: string
  display_name: string
  unit: NutrientUnit
  category: 'macro' | 'mineral' | 'vitamin'
  kind: NutrientKind
  /** EAR adequacy floor; null where ICMR publishes only an AI. */
  ear: number | null
  /** The published RDA/AI, before any compensation. */
  rda: number
  /** Tolerable Upper Limit; null where ICMR deliberately set none. */
  tul: number | null
  /** RDA after the compensation ledger — what today actually asks of you. */
  target_effective: number
  /** What the ledger added to today. 0 for most nutrients on most days. */
  carried_in: number
  /** Weekday the carry came from, e.g. "Friday". Null when carried_in is 0. */
  carried_from: string | null
  consumed: number
  /**
   * The share of the day's food weight that actually carried a figure for this
   * nutrient, 0 to 1.
   *
   * 0 means nothing measured it, so `consumed` is silence rather than zero — the
   * distinction that stops a gap in the food tables reading as a deficit. Iodine
   * is the sharpest case: it reaches the database on iodised salt and almost
   * nothing else.
   */
  coverage: number
}

/**
 * Day-level notes from `resolve_day`. `above-limit` is not one of them — it is a
 * per-nutrient status, not a day-level warning — and is kept out for that reason.
 *
 * - `calorie-recalibrated`: weigh-ins moved the energy target off the formula.
 * - `reference-framework`: iron is the IOM figure after menopause, not ICMR's.
 * - `approaching-limit`: after menopause, a day's iron is near the upper limit.
 */
export type WarningKind =
  | 'condition-conflict'
  | 'medication-timing'
  | 'drug-interaction'
  | 'calorie-recalibrated'
  | 'reference-framework'
  | 'approaching-limit'

export interface TodayWarning {
  kind: WarningKind
  message: string
}

export interface TodayTargets {
  date: string
  nutrients: NutrientProgress[]
  warnings: TodayWarning[]
}
