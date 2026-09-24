import type { CycleState } from '../../cycle/types'
import type { ReminderSettings } from '../../settings/types'
import type { WeightTrend } from '../../weight/types'

export const WEIGHT_FIXTURE: WeightTrend = {
  weigh_ins: [
    { date: '2026-07-19', weight_kg: 74.8 },
    { date: '2026-07-26', weight_kg: 74.9 },
    { date: '2026-08-02', weight_kg: 74.4 },
    { date: '2026-08-09', weight_kg: 74.1 },
    { date: '2026-08-16', weight_kg: 74.2 },
  ],
  smoothed_kg: 74.2,
  goal: 'lose',
  expected_kg_per_week: -0.4,
  observed_kg_per_week: -0.1,
  calorie_target_kcal: 2020,
  adjustment: {
    delta_kcal: -90,
    since: '2026-08-16',
    reason:
      'Your weight has fallen about 0.1 kg a week against a goal of losing about 0.4 kg a week, so your calorie target moves down a bounded step. It stays within 10% of what the formula gives and never goes below a safe floor.',
  },
  note: 'Your target last moved on 16 August. The next reading needs three weigh-ins across at least two weeks after that.',
}

export const CYCLE_FIXTURE: CycleState = {
  enabled: true,
  last_period_start: '2026-08-14',
  logs: [
    { date: '2026-08-14', flow: 'medium' },
    { date: '2026-08-15', flow: 'heavy' },
    { date: '2026-08-16', flow: 'medium' },
  ],
  coaching: [
    {
      id: 'coffee-timing',
      title: 'Keep coffee and tea an hour away from meals',
      body: 'In young Indian women, one cup of tea with a rice meal cut iron absorption by about 49%, and two cups by about 67%. A one-hour gap roughly halves that.',
      evidence: 'strong',
    },
    {
      id: 'vitamin-c',
      title: 'Pair iron-rich meals with lemon, tomato, tamarind or guava',
      body: 'Vitamin C markedly improves absorption of the non-haem iron in a rice-and-dal meal. This changes what to eat alongside, not how much iron you need.',
      evidence: 'moderate',
    },
    {
      id: 'calcium',
      title: 'Calcium at 1,000–1,200 mg a day',
      body: 'The only nutrient both ACOG and RCOG endorse for PMS. Typical intake among Indian women is around 270–500 mg. The trial took three cycles to show benefit, so give it time.',
      evidence: 'moderate',
    },
    {
      id: 'ginger',
      title: 'Dry ginger (sukku) 750–2,000 mg on days 1–3',
      body: 'Comparable to mefenamic acid and ibuprofen in head-to-head trials for period pain. NSAIDs still outperform every dietary option — this is not a substitute for treatment.',
      evidence: 'moderate',
    },
  ],
  referral: null,
}

export const REMINDERS_FIXTURE: ReminderSettings = {
  push_granted: false,
  slots: [
    { slot: 'breakfast', time: '08:00', weekend_time: '09:30', reminder_on: true },
    { slot: 'snack1', time: '11:00', weekend_time: null, reminder_on: false },
    { slot: 'lunch', time: '13:30', weekend_time: '14:00', reminder_on: true },
    { slot: 'snack2', time: '17:00', weekend_time: null, reminder_on: true },
    { slot: 'dinner', time: '20:30', weekend_time: null, reminder_on: true },
  ],
}
