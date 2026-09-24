import type { DayState, ReportDay, WeeklyReport } from '../../report/types'

function day(
  date: string,
  weekday: string,
  state: DayState,
  energy_kcal: number,
  target_kcal: number,
): ReportDay {
  return { date, weekday, state, energy_kcal, target_kcal }
}

/**
 * A week that went partly wrong, which is the only kind worth designing for.
 *
 * - Nothing was logged on Tuesday.
 * - A weigh-in on Thursday stepped the energy target down 210 kcal from that day on.
 * - Calcium and fibre fell short, and part of each expired past the carry cap.
 * - Protein was short on days it can never carry.
 * - Sodium ran over its ceiling.
 * - A quarter of the week's energy was estimated.
 *
 * The figures follow the backend's rounding: kcal whole, amounts to one decimal,
 * coverage to two.
 */
export const REPORT_FIXTURE: WeeklyReport = {
  start_date: '2026-08-16',
  end_date: '2026-08-22',
  status: 'complete',
  tracked_days: 6,
  slots: { logged: 26, skipped: 3, expected: 35 },
  measured_kcal: 9160,
  estimated_kcal: 2980,
  plan: { planned: 28, followed: 17 },
  days: [
    day('2026-08-16', 'Sun', 'tracked', 2240, 2105),
    day('2026-08-17', 'Mon', 'tracked', 1420, 2105),
    day('2026-08-18', 'Tue', 'untracked', 0, 2105),
    day('2026-08-19', 'Wed', 'tracked', 1960, 2105),
    day('2026-08-20', 'Thu', 'tracked', 2310, 1895),
    day('2026-08-21', 'Fri', 'tracked', 1870, 1895),
    day('2026-08-22', 'Sat', 'tracked', 2340, 1895),
  ],
  nutrients: [
    {
      code: 'fibre',
      display_name: 'Dietary fibre',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 5,
      target_total: 151.6,
      ear_total: null,
      consumed_total: 118.4,
      days_met: 1,
      days_over_limit: 0,
      coverage: 0.86,
    },
    {
      code: 'energy',
      display_name: 'Energy',
      unit: 'kcal',
      category: 'macro',
      kind: 'target',
      measured_days: 6,
      target_total: 12002.0,
      ear_total: null,
      consumed_total: 12140.0,
      days_met: 3,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 6,
      target_total: 323.7,
      ear_total: 257.4,
      consumed_total: 296.4,
      days_met: 3,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 6,
      target_total: 6000.0,
      ear_total: 4800.0,
      consumed_total: 3710.0,
      days_met: 1,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'iron',
      display_name: 'Iron',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 6,
      target_total: 114.0,
      ear_total: 66.0,
      consumed_total: 105.2,
      days_met: 4,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'sodium',
      display_name: 'Sodium',
      unit: 'mg',
      category: 'mineral',
      kind: 'ceiling',
      measured_days: 6,
      target_total: 12000.0,
      ear_total: null,
      consumed_total: 14820.0,
      days_met: 2,
      days_over_limit: 0,
      coverage: 0.91,
    },
    {
      code: 'vitamin_b12',
      display_name: 'Vitamin B12',
      unit: 'ug',
      category: 'vitamin',
      kind: 'target',
      measured_days: 6,
      target_total: 15.0,
      ear_total: 12.0,
      consumed_total: 21.8,
      days_met: 5,
      days_over_limit: 0,
      coverage: 0.62,
    },
  ],
  uncompensated: [
    {
      code: 'fibre',
      display_name: 'Dietary fibre',
      unit: 'g',
      amount: 22.6,
      reason_code: 'cap',
      reason: 'Beyond the 25% a day can carry, so it expired.',
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      amount: 57.0,
      reason_code: 'not_compensable',
      reason: 'Protein has no storage pool, so a short day is not carried forward.',
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      amount: 1240.0,
      reason_code: 'cap',
      reason: 'Beyond the 30% a day can carry, so it expired.',
    },
  ],
  suggestions: [
    {
      nutrient_code: 'calcium',
      display_name: 'Calcium',
      text:
        'Calcium fell short this week. ' +
        'Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam.',
      foods: [
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a01', name: 'Ragi mudde' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a02', name: 'Curd rice' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a03', name: 'Moong dal payasam' },
      ],
    },
    {
      nutrient_code: 'fibre',
      display_name: 'Dietary fibre',
      text: 'Dietary fibre fell short this week. Dishes that carry it: Sundal, Keerai kootu.',
      foods: [
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a04', name: 'Sundal' },
        { food_id: '0b7f3c52-5a4e-4d0e-9a51-6f1d2c3b4a05', name: 'Keerai kootu' },
      ],
    },
  ],
}

/**
 * The week after, opened on its Wednesday. Sunday and Monday were logged and
 * Tuesday was not. Today and the rest of the week still count for nothing.
 * Two tracked days are too few for a suggestion.
 */
export const IN_PROGRESS_REPORT_FIXTURE: WeeklyReport = {
  start_date: '2026-08-23',
  end_date: '2026-08-29',
  status: 'in-progress',
  tracked_days: 2,
  slots: { logged: 8, skipped: 1, expected: 15 },
  measured_kcal: 3790,
  estimated_kcal: 400,
  plan: { planned: 12, followed: 7 },
  days: [
    day('2026-08-23', 'Sun', 'tracked', 1980, 1895),
    day('2026-08-24', 'Mon', 'tracked', 2210, 1895),
    day('2026-08-25', 'Tue', 'untracked', 0, 1895),
    day('2026-08-26', 'Wed', 'in-progress', 0, 1895),
    day('2026-08-27', 'Thu', 'future', 0, 1895),
    day('2026-08-28', 'Fri', 'future', 0, 1895),
    day('2026-08-29', 'Sat', 'future', 0, 1895),
  ],
  nutrients: [
    {
      code: 'energy',
      display_name: 'Energy',
      unit: 'kcal',
      category: 'macro',
      kind: 'target',
      measured_days: 2,
      target_total: 3790.7,
      ear_total: null,
      consumed_total: 4190.0,
      days_met: 2,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      measured_days: 2,
      target_total: 107.9,
      ear_total: 85.8,
      consumed_total: 110.2,
      days_met: 2,
      days_over_limit: 0,
      coverage: 1.0,
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      measured_days: 2,
      target_total: 2000.0,
      ear_total: 1600.0,
      consumed_total: 1410.0,
      days_met: 1,
      days_over_limit: 0,
      coverage: 1.0,
    },
  ],
  uncompensated: [],
  suggestions: [],
}
