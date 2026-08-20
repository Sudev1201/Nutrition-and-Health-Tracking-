import { SLOT_ORDER } from '../log/types'
import type { MealSlot } from '../log/types'
import type { ConditionCode, OnboardingAnswers } from './types'

export type StepId =
  | 'about'
  | 'goal'
  | 'diet'
  | 'conditions'
  | 'observance'
  | 'preferences'
  | 'mealtimes'
  | 'usual'

export const STEP_ORDER: readonly StepId[] = [
  'about',
  'goal',
  'diet',
  'conditions',
  'observance',
  'preferences',
  'mealtimes',
  'usual',
]

export const STEP_TITLES: Record<StepId, string> = {
  about: 'About you',
  goal: 'Your goal',
  diet: 'How you eat',
  conditions: 'Health conditions',
  observance: 'Vegetarian days',
  preferences: 'Foods you like and avoid',
  mealtimes: 'When you eat',
  usual: 'What you usually eat',
}

/**
 * Typical South Indian meal times, so the step opens filled in rather than as
 * five blank clocks. They are only a starting point — everyone's day differs and
 * a reminder at the wrong hour is worse than none, so they stay editable.
 */
export const DEFAULT_MEAL_TIMES: Record<MealSlot, string> = {
  breakfast: '08:00',
  snack1: '11:00',
  lunch: '13:30',
  snack2: '17:00',
  dinner: '20:30',
}

export function emptyAnswers(): OnboardingAnswers {
  return {
    sex: null,
    age: '',
    weight_kg: '',
    activity: null,
    goal: null,
    pace: null,
    diet_type: null,
    cereal_dominant: false,
    conditions: [],
    medications: [],
    observances: [],
    avoided: [],
    favourites: [],
    meal_times: SLOT_ORDER.map((slot) => ({
      slot,
      time: DEFAULT_MEAL_TIMES[slot],
      weekend_time: null,
    })),
    usual_intake: [],
  }
}

/**
 * Condition pairs that give opposite instructions. The spec forbids averaging
 * these — hypertension tightens sodium to 1,500 mg while symptomatic hypotension
 * calls for 6-10 g of salt a day, and silently splitting the difference would
 * serve neither. They are surfaced for clinician review instead.
 */
const CONFLICTING_PAIRS: readonly [ConditionCode, ConditionCode][] = [
  ['hypertension', 'hypotension'],
  ['hypothyroidism', 'hyperthyroidism'],
]

export function hasConditionConflict(conditions: ConditionCode[]): boolean {
  return CONFLICTING_PAIRS.some(
    ([one, other]) => conditions.includes(one) && conditions.includes(other),
  )
}

function numberIn(value: string, low: number, high: number): boolean {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed >= low && parsed <= high
}

/** Returns an error message, or null when the step may be left. */
export function validateStep(step: StepId, answers: OnboardingAnswers): string | null {
  switch (step) {
    case 'about': {
      if (answers.sex === null) return 'Please choose an option, so the right reference values are used.'
      if (!numberIn(answers.age, 1, 120)) return 'Please give an age between 1 and 120.'
      // Energy is computed from weight, so a typo here quietly skews every target.
      if (!numberIn(answers.weight_kg, 20, 300)) return 'Please give a weight in kg between 20 and 300.'
      if (answers.activity === null) return 'Please choose an activity level.'
      return null
    }

    case 'goal': {
      if (answers.goal === null) return 'Please choose a goal.'
      if (answers.goal !== 'maintain' && answers.pace === null) return 'Please choose a pace.'
      return null
    }

    case 'diet':
      return answers.diet_type === null ? 'Please choose how you eat.' : null

    case 'conditions': {
      const incomplete = answers.medications.some(
        (medication) => medication.name.trim() === '' || medication.time.trim() === '',
      )
      // A medication without a dose time cannot be checked against meal times,
      // which is the whole reason medications are collected.
      return incomplete ? 'Every medication needs a name and the time you take it.' : null
    }

    case 'mealtimes': {
      const missing = answers.meal_times.some((meal) => meal.time.trim() === '')
      return missing ? 'Please give a usual time for each meal.' : null
    }

    // Nothing here is required: observances, allergies and favourites are all
    // optional, and the usual-intake wizard is explicitly skippable.
    case 'observance':
    case 'preferences':
    case 'usual':
      return null
  }
}
