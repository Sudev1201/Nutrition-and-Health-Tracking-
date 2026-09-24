import type { MealSlot } from '../log/types'

/**
 * PROPOSED CONTRACT for `GET/PUT /profile` — implemented by plan 4.
 *
 * Note what is NOT collected: height. The ICMR-NIN energy equations are
 * weight-based, and the spec found reference heights could not be verified
 * against any primary source, so asking for one would imply a precision the
 * science does not have.
 */

export type Sex = 'female' | 'male'
export type ActivityLevel = 'sedentary' | 'moderate' | 'heavy'
export type Goal = 'lose' | 'maintain' | 'gain'
export type Pace = 'gentle' | 'steady'
export type DietType = 'vegetarian' | 'eggetarian' | 'fishetarian' | 'non-vegetarian'

/**
 * Asked of women only. ICMR's 29 mg iron figure for women averages menstrual
 * loss; ICMR publishes no postmenopausal category, so after menopause the IOM
 * figure applies instead, with a note on Today saying so.
 */
export type MenstrualStatus = 'menstruating' | 'postmenopausal'

export type ConditionCode =
  | 'type2_diabetes'
  | 'prediabetes'
  | 'high_cholesterol'
  | 'hypertension'
  | 'hypotension'
  | 'hypothyroidism'
  | 'hyperthyroidism'

export const CONDITION_LABELS: Record<ConditionCode, string> = {
  type2_diabetes: 'Type 2 diabetes',
  prediabetes: 'Prediabetes',
  high_cholesterol: 'High cholesterol',
  hypertension: 'High blood pressure',
  hypotension: 'Low blood pressure (diagnosed, with symptoms)',
  hypothyroidism: 'Hypothyroidism',
  hyperthyroidism: 'Hyperthyroidism',
}

/*
 * Display labels for the coded answers.
 *
 * These live here rather than as `<option>` text inside the wizard because the
 * profile summary has to render the same answers read-only. When the wizard was
 * the only thing showing them, the words existed only in its markup — and a
 * summary that retyped them would be free to disagree with the form.
 *
 * The hints are the explanatory halves the wizard appends; a summary shows the
 * label alone, since it is reporting a choice rather than helping make one.
 */

export const SEX_LABELS: Record<Sex, string> = {
  female: 'Female',
  male: 'Male',
}

export const MENSTRUAL_STATUS_LABELS: Record<MenstrualStatus, string> = {
  menstruating: 'Yes, I have periods',
  postmenopausal: 'No, I am past menopause',
}

export const ACTIVITY_LABELS: Record<ActivityLevel, string> = {
  sedentary: 'Sedentary',
  moderate: 'Moderate',
  heavy: 'Heavy',
}

export const ACTIVITY_HINTS: Record<ActivityLevel, string> = {
  sedentary: 'desk work, little exercise',
  moderate: 'on your feet, or regular exercise',
  heavy: 'manual work or hard training',
}

export const GOAL_LABELS: Record<Goal, string> = {
  lose: 'Lose weight',
  maintain: 'Maintain',
  gain: 'Gain weight',
}

export const PACE_LABELS: Record<Pace, string> = {
  gentle: 'Gentle',
  steady: 'Steady',
}

export const PACE_HINTS: Record<Pace, string> = {
  gentle: 'about 0.25 kg a week',
  steady: 'about 0.5 kg a week',
}

export const DIET_LABELS: Record<DietType, string> = {
  vegetarian: 'Vegetarian',
  eggetarian: 'Vegetarian, plus egg',
  fishetarian: 'Vegetarian, plus fish',
  'non-vegetarian': 'Non-vegetarian',
}

export interface Medication {
  name: string
  /** "HH:MM". Load-bearing: the levothyroxine window is checked against it. */
  time: string
}

export interface ObservanceRule {
  kind: 'weekday' | 'date_range' | 'single_date'
  /** 0-6 for a weekday rule. */
  weekday: number | null
  start_date: string | null
  end_date: string | null
  label: string
}

/** A liked or avoided food. `food_id` is set when picked from search. */
export interface FoodRefAnswer {
  label: string
  food_id: string | null
  food_kind: 'dish' | 'ingredient' | null
}

/**
 * One item of a typical day. A food reference with a weight, not a description —
 * free text cannot be costed against the food database, which is why the app
 * could collect "what I usually eat" and still not know the calories.
 */
export interface UsualIntakeAnswer {
  slot: MealSlot
  label: string
  food_id: string
  food_kind: 'dish' | 'ingredient'
  grams: number
}

export interface MealTimeAnswer {
  slot: MealSlot
  time: string
  weekend_time: string | null
  /**
   * Whether this slot is part of a normal day. Only the two snacks are ever
   * switched off — four or five meals means one or two snacks, and a day without
   * lunch is a skipped lunch rather than a meal-count preference.
   */
  is_enabled: boolean
}

export interface OnboardingAnswers {
  sex: Sex | null
  /** Null for a man, and until a woman answers. */
  menstrual_status: MenstrualStatus | null
  age: string
  weight_kg: string
  activity: ActivityLevel | null

  goal: Goal | null
  pace: Pace | null

  diet_type: DietType | null
  /**
   * ICMR footnotes that a cereal-based diet with low-quality protein needs
   * 1 g/kg/day rather than 0.83. A rice-dominant diet without adequate pulses
   * and milk is exactly that case.
   */
  cereal_dominant: boolean

  conditions: ConditionCode[]
  medications: Medication[]

  observances: ObservanceRule[]
  /** Allergies and anything else the user would rather not eat. A hard block. */
  avoided: FoodRefAnswer[]
  favourites: FoodRefAnswer[]

  meal_times: MealTimeAnswer[]
  usual_intake: UsualIntakeAnswer[]
}
