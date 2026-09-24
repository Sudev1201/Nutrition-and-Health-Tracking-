import type { NutrientUnit } from '../lib/format'
import type { NutrientKind } from '../lib/status'

/**
 * CONTRACT for `GET /reports/week?start=` — plan 8.
 *
 * `start` must be a Sunday no later than the current week's, or the answer is a
 * 422. A missing profile is a 404. The report is derived on every request and
 * never stored.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec:
 * - a week still going has its own status;
 * - each day says whether it was tracked;
 * - every total counts only the days that measured it;
 * - meals are logged, skipped or missed, and a stored plan's adherence is given;
 * - an expired shortfall carries a reason code as well as words;
 * - a suggestion names the dishes it proposes.
 */

/** `complete` once the Saturday has ended where the user is. */
export type ReportStatus = 'complete' | 'in-progress'

/**
 * - `tracked`: over, with something logged. Only these count in any total.
 * - `untracked`: over, with nothing logged. Silence, not a day of eating nothing.
 * - `in-progress`: today. It counts once it is over.
 * - `future`: still to come.
 */
export type DayState = 'tracked' | 'untracked' | 'in-progress' | 'future'

export interface ReportDay {
  date: string
  /** "Sun" to "Sat". */
  weekday: string
  state: DayState
  /** Whole kcal. 0 on every day that is not tracked. */
  energy_kcal: number
  /** That day's own energy target before any carry, at the recalibration then in force. */
  target_kcal: number
}

export interface SlotCounts {
  logged: number
  /** "Nothing eaten here": accounted for, not missed. */
  skipped: number
  /** The slots enabled now, on every day that has ended. The rest were missed. */
  expected: number
}

export interface PlanAdherence {
  /** Planned meals on the days that have ended. */
  planned: number
  /** Of those, the slots logged with the planned dish. */
  followed: number
}

export interface ReportNutrient {
  code: string
  display_name: string
  unit: NutrientUnit
  category: 'macro' | 'mineral' | 'vitamin'
  kind: NutrientKind
  /** Tracked days on which something logged carried a figure for it. */
  measured_days: number
  /**
   * Each measured day's base target, before carries, summed. Summing the
   * effective targets would count a made-up shortfall twice.
   */
  target_total: number
  /** The EAR over the same days, summed. Null where there is no EAR. */
  ear_total: number | null
  consumed_total: number
  /** Measured days in Today's "on target" band. */
  days_met: number
  /**
   * Measured days at or past the daily *upper limit* (TUL) only -- always 0 for a
   * ceiling nutrient, which has no TUL of its own (sodium's daily figure is
   * already its ceiling). No weekly sum is set against it.
   *
   * A ceiling's own days over its limit are not carried in this field: derive
   * them as `measured_days - days_met` (`kind === 'ceiling'`), which is exactly
   * the days the day's own consumption reached its effective ceiling.
   */
  days_over_limit: number
  /** Mean share of each measured day's food weight that carried a figure for it, 0 to 1. */
  coverage: number
}

/**
 * A shortfall the ledger could not make up, summed over the week. The spec
 * requires the report to show these rather than quietly drop them. Energy never
 * appears here, and neither does anything held steady.
 */
export interface UncompensatedGap {
  code: string
  display_name: string
  unit: NutrientUnit
  amount: number
  /** `not_compensable`: never carried, as protein. `cap`: beyond what a day may carry. */
  reason_code: 'not_compensable' | 'cap'
  reason: string
}

export interface SuggestedFood {
  food_id: string
  name: string
}

/**
 * A nutrient that fell short, with dishes from the plan's own pool that carry it.
 * The next week's plan weighs these nutrients more.
 */
export interface Suggestion {
  nutrient_code: string
  display_name: string
  text: string
  foods: SuggestedFood[]
}

export interface WeeklyReport {
  start_date: string
  end_date: string
  status: ReportStatus
  tracked_days: number
  slots: SlotCounts
  /** Energy from entries not marked estimated, over tracked days. */
  measured_kcal: number
  /** Energy from entries marked estimated: eaten out, or eyeballed. */
  estimated_kcal: number
  /** Null when the week has no stored plan. */
  plan: PlanAdherence | null
  days: ReportDay[]
  /** Macros, then minerals, then vitamins, each by name. */
  nutrients: ReportNutrient[]
  uncompensated: UncompensatedGap[]
  /** At most three, worst first. */
  suggestions: Suggestion[]
}
