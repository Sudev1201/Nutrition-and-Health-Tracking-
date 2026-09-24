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
  eligible: true,
  ineligible_reason: null,
  enabled: true,
  has_history: true,
  last_period_start: '2026-08-14',
  days: [
    { date: '2026-08-16', flow: 'medium', symptoms: [] },
    { date: '2026-08-15', flow: 'heavy', symptoms: ['cramps'] },
    { date: '2026-08-14', flow: 'medium', symptoms: ['bloating', 'cramps'] },
  ],
  screening: null,
  coaching: [
    {
      id: 'coffee-timing',
      title: 'Keep coffee and tea an hour away from meals',
      body: 'In young Indian women, one cup of tea with a rice meal cut iron absorption by about 49%, and two cups by about 67%. A one-hour gap roughly halves that.',
      evidence: 'strong',
    },
    {
      id: 'vitamin-c',
      title: 'Pair iron-rich meals with lemon, tomato, tamarind, amla or guava',
      body: 'Around your period, have something rich in vitamin C with the meal that carries your iron. This changes what to eat alongside, not how much iron you need.',
      evidence: 'mechanistic',
    },
    {
      id: 'ginger',
      title: 'Dry ginger (sukku), 750–2,000 mg a day on days 1–3',
      body: 'About half to one level teaspoon of dry ginger powder a day, on the first three days only. Painkillers such as ibuprofen still work better than any food. This is not a substitute for treatment.',
      evidence: 'moderate',
    },
    {
      id: 'calcium',
      title: 'Calcium at 1,000–1,200 mg a day',
      body: 'The only nutrient both ACOG and RCOG endorse for PMS. The trial took three cycles to show benefit, so give it time.',
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
