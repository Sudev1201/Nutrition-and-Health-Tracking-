import type { Diary } from '../../log/types'

/**
 * A real weekday: breakfast and lunch logged, the optional mid-morning snack
 * deliberately skipped, an estimated restaurant entry at the evening snack, and
 * dinner still to come.
 */
export const DIARY_FIXTURE: Diary = {
  date: '2026-08-17',
  slots: [
    {
      slot: 'breakfast',
      time: '08:00',
      state: 'logged',
      entries: [
        {
          id: 'e1',
          name: 'Idli',
          portion: '3 idli',
          measure_name: 'idli',
          quantity: 3,
          grams: 120,
          is_estimated: false,
          energy_kcal: 174,
        },
        {
          id: 'e2',
          name: 'Sambar',
          portion: '1 katori',
          measure_name: 'katori',
          quantity: 1,
          grams: 150,
          is_estimated: false,
          energy_kcal: 128,
        },
      ],
    },
    {
      // Skipped, not forgotten -- the snack slot is optional by design and must
      // not nag someone who rarely eats it.
      slot: 'snack1',
      time: '11:00',
      state: 'skipped',
      entries: [],
    },
    {
      slot: 'lunch',
      time: '13:30',
      state: 'logged',
      entries: [
        {
          id: 'e3',
          name: 'Rice, cooked',
          portion: '1½ cup',
          measure_name: 'cup',
          quantity: 1.5,
          grams: 240,
          is_estimated: false,
          energy_kcal: 312,
        },
        {
          id: 'e4',
          name: 'Vatha kuzhambu',
          portion: '1 katori',
          measure_name: 'katori',
          quantity: 1,
          grams: 120,
          is_estimated: false,
          energy_kcal: 96,
        },
        {
          id: 'e5',
          name: 'Appalam',
          portion: '2 piece',
          measure_name: 'piece',
          quantity: 2,
          grams: 26,
          is_estimated: false,
          energy_kcal: 104,
        },
      ],
    },
    {
      slot: 'snack2',
      time: '17:00',
      state: 'logged',
      entries: [
        {
          id: 'e6',
          name: 'Filter coffee',
          portion: '1 tumbler',
          measure_name: 'tumbler',
          quantity: 1,
          grams: null,
          is_estimated: true,
          energy_kcal: 90,
        },
      ],
    },
    {
      slot: 'dinner',
      time: '20:30',
      state: 'empty',
      entries: [],
    },
  ],
}
