/**
 * `answersFromProfile` is the seam where a saved profile becomes wizard state,
 * and every field it forgets to carry is silently destroyed by the next save —
 * because `PUT /profile` replaces the whole questionnaire rather than merging.
 * These tests pin the fields that a round trip must preserve.
 */
import { expect, test } from 'vitest'
import { answersFromProfile } from './useProfile'
import type { SavedProfile } from './useProfile'

const WEDNESDAY = {
  kind: 'weekday' as const,
  weekday: 3,
  start_date: null,
  end_date: null,
  label: 'No meat on Wednesdays',
}

const PURATTASI = {
  kind: 'date_range' as const,
  weekday: null,
  start_date: '2026-09-18',
  end_date: '2026-10-17',
  label: 'Purattasi',
}

function savedProfile(overrides: Partial<SavedProfile> = {}): SavedProfile {
  return {
    sex: 'male',
    age: 25,
    weight_kg: 65,
    activity: 'sedentary',
    goal: 'maintain',
    pace: null,
    diet_type: 'vegetarian',
    cereal_dominant: false,
    conditions: [],
    medications: [],
    meal_times: [],
    observances: [],
    avoided: [],
    favourites: [],
    usual_intake: [],
    ...overrides,
  }
}

test('a saved observance is carried into the wizard state', () => {
  const answers = answersFromProfile(savedProfile({ observances: [WEDNESDAY] }))

  expect(answers.observances).toEqual([WEDNESDAY])
})

test('all three observance shapes are carried', () => {
  const festival = {
    kind: 'single_date' as const,
    weekday: null,
    start_date: '2026-11-08',
    end_date: null,
    label: 'Karthigai Deepam',
  }

  const answers = answersFromProfile(
    savedProfile({ observances: [WEDNESDAY, PURATTASI, festival] }),
  )

  expect(answers.observances.map((item) => item.label)).toEqual([
    'No meat on Wednesdays',
    'Purattasi',
    'Karthigai Deepam',
  ])
})

test('a profile with no observances still yields an empty list, not undefined', () => {
  const answers = answersFromProfile(savedProfile())

  expect(answers.observances).toEqual([])
})
