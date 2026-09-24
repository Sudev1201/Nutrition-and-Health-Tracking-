import { expect, test } from 'vitest'
import { emptyAnswers, hasConditionConflict, validateStep } from './validation'

function answers(overrides: Partial<ReturnType<typeof emptyAnswers>> = {}) {
  return { ...emptyAnswers(), ...overrides }
}

test('the about step needs sex, age, weight and activity', () => {
  expect(validateStep('about', answers())).not.toBeNull()
})

test('the about step passes once all four are given', () => {
  expect(
    validateStep(
      'about',
      answers({ sex: 'male', age: '34', weight_kg: '74.2', activity: 'moderate' }),
    ),
  ).toBeNull()
})

// The energy equation is weight-based, so an implausible weight silently
// produces an implausible calorie target rather than an obvious error.
test('an implausible weight is rejected', () => {
  expect(
    validateStep(
      'about',
      answers({ sex: 'male', age: '34', weight_kg: '740', activity: 'moderate' }),
    ),
  ).toMatch(/weight/i)
})

test('a non-numeric age is rejected', () => {
  expect(
    validateStep(
      'about',
      answers({ sex: 'male', age: 'thirty', weight_kg: '74', activity: 'moderate' }),
    ),
  ).toMatch(/age/i)
})

test('a goal to lose or gain needs a pace', () => {
  expect(validateStep('goal', answers({ goal: 'lose' }))).toMatch(/pace/i)
})

test('maintaining needs no pace', () => {
  expect(validateStep('goal', answers({ goal: 'maintain' }))).toBeNull()
})

/*
 * The dose time is not a note — the planner checks breakfast against it to
 * enforce the 60-minute levothyroxine window. A medication without a time makes
 * that check impossible, so it cannot be saved half-filled.
 */
test('a medication without a dose time is rejected', () => {
  expect(
    validateStep('conditions', answers({ medications: [{ name: 'Levothyroxine', time: '' }] })),
  ).toMatch(/time/i)
})

test('having no conditions at all is fine', () => {
  expect(validateStep('conditions', answers())).toBeNull()
})

/*
 * Meal times open pre-filled with typical South Indian times, so the step is a
 * confirmation rather than five blank clocks. They remain editable, since a
 * reminder at the wrong hour is worse than none.
 */
test('meal times start pre-populated', () => {
  const times = emptyAnswers().meal_times

  expect(times.map((meal) => meal.time)).toEqual([
    '08:00',
    '11:00',
    '13:30',
    '17:00',
    '20:30',
  ])
})

test('the pre-filled meal times pass validation as they stand', () => {
  expect(validateStep('mealtimes', answers())).toBeNull()
})

test('a meal time the user clears is still rejected', () => {
  const cleared = answers()
  cleared.meal_times[2] = { ...cleared.meal_times[2], time: '' }

  expect(validateStep('mealtimes', cleared)).toMatch(/time/i)
})

test('the usual-intake step can be skipped', () => {
  expect(validateStep('usual', answers())).toBeNull()
})

/*
 * Hypertension and hypotension give opposite sodium instructions. The spec is
 * explicit that the app must surface a conflict for clinician review rather than
 * silently averaging the two targets.
 */
test('hypertension with hypotension is a conflict', () => {
  expect(hasConditionConflict(['hypertension', 'hypotension'])).toBe(true)
})

test('hypothyroidism with hyperthyroidism is a conflict', () => {
  expect(hasConditionConflict(['hypothyroidism', 'hyperthyroidism'])).toBe(true)
})

test('ordinary combinations are not conflicts', () => {
  expect(hasConditionConflict(['type2_diabetes', 'high_cholesterol'])).toBe(false)
})

// ICMR's 29 mg iron figure for women averages menstrual loss; after menopause a
// different figure applies. So a woman is asked, and a man is not.
test('a woman is asked whether she still has periods', () => {
  expect(
    validateStep(
      'about',
      answers({ sex: 'female', age: '52', weight_kg: '60', activity: 'moderate' }),
    ),
  ).toMatch(/periods/i)
})

test('a woman who answers it may continue', () => {
  expect(
    validateStep(
      'about',
      answers({
        sex: 'female',
        age: '52',
        weight_kg: '60',
        activity: 'moderate',
        menstrual_status: 'postmenopausal',
      }),
    ),
  ).toBeNull()
})

test('a man is not asked about periods', () => {
  expect(
    validateStep('about', answers({ sex: 'male', age: '34', weight_kg: '74.2', activity: 'moderate' })),
  ).toBeNull()
})

// The spec's own example: the optional mid-morning snack should not nag someone
// who rarely eats it. So its reminder starts off, and every other slot's on.
test('a new questionnaire reminds about every meal but the mid-morning snack', () => {
  expect(emptyAnswers().meal_times.map((meal) => [meal.slot, meal.reminder_on])).toEqual([
    ['breakfast', true],
    ['snack1', false],
    ['lunch', true],
    ['snack2', true],
    ['dinner', true],
  ])
})
