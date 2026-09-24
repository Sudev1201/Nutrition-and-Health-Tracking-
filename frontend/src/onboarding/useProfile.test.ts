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
    menstrual_status: null,
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

// Carried explicitly: PUT /profile replaces rather than merges, so a status left
// out here would be wiped by the next save of any other section.
test('the menstrual status is carried into the wizard state', () => {
  const answers = answersFromProfile(
    savedProfile({ sex: 'female', menstrual_status: 'postmenopausal' }),
  )
  expect(answers.menstrual_status).toBe('postmenopausal')
})

function mealTime(slot: string, reminder_on: boolean) {
  return { slot, time: '08:00', weekend_time: null, reminder_on, is_enabled: true }
}

// The Reminders screen sets reminder_on, but it rides on the meal-time rows that
// PUT /profile rewrites. Carried here, a save of any other section sends each
// slot's setting back as it was.
test('each slot keeps its saved reminder setting', () => {
  const answers = answersFromProfile(
    savedProfile({
      meal_times: [
        mealTime('breakfast', true),
        mealTime('snack1', true),
        mealTime('lunch', false),
        mealTime('snack2', true),
        mealTime('dinner', true),
      ],
    }),
  )

  expect(answers.meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', true],
    ['lunch', false],
    ['snack2', true],
    ['dinner', true],
  ])
})

test('a slot with no saved row gets the default reminder', () => {
  const answers = answersFromProfile(savedProfile({ meal_times: [] }))

  expect(answers.meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', false],
    ['lunch', true],
    ['snack2', true],
    ['dinner', true],
  ])
})
