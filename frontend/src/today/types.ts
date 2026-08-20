import type { NutrientUnit } from '../lib/format'
import type { NutrientKind } from '../lib/status'

/**
 * PROPOSED CONTRACT for `GET /targets/today?date=` — implemented by plans 3-4.
 * The mock handler in `src/mocks/handlers/targets.ts` is the executable version
 * of this shape; when the backend lands, delete the handler, not these types.
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
}

export type WarningKind = 'condition-conflict' | 'above-limit' | 'medication-timing'

export interface TodayWarning {
  kind: WarningKind
  message: string
}

export interface TodayTargets {
  date: string
  nutrients: NutrientProgress[]
  warnings: TodayWarning[]
}
