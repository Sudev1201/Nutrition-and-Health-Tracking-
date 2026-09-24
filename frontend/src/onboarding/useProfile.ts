import { useQuery } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'
import { SLOT_ORDER } from '../log/types'
import type { MealSlot } from '../log/types'
import type {
  FoodRefAnswer,
  ObservanceRule,
  OnboardingAnswers,
  UsualIntakeAnswer,
} from './types'
import { DEFAULT_MEAL_TIMES, emptyAnswers, reminderOnByDefault } from './validation'

/** `GET /profile` — the saved answers, or null when onboarding is not done. */
export interface SavedProfile {
  sex: OnboardingAnswers['sex']
  menstrual_status: OnboardingAnswers['menstrual_status']
  age: number
  weight_kg: number
  activity: OnboardingAnswers['activity']
  goal: OnboardingAnswers['goal']
  pace: OnboardingAnswers['pace']
  diet_type: OnboardingAnswers['diet_type']
  cereal_dominant: boolean
  conditions: OnboardingAnswers['conditions']
  medications: { name: string; time: string }[]
  meal_times: {
    slot: string
    time: string
    weekend_time: string | null
    reminder_on: boolean
    is_enabled: boolean
  }[]
  observances: ObservanceRule[]
  avoided: FoodRefAnswer[]
  favourites: FoodRefAnswer[]
  usual_intake: UsualIntakeAnswer[]
}

export function useProfile() {
  return useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      try {
        return await api.get<SavedProfile>('/profile')
      } catch (error) {
        // 404 is the documented "not onboarded yet" answer, not a failure.
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    retry: false,
  })
}

/**
 * Saved profile -> wizard state.
 *
 * The form holds numbers as strings because they come from text inputs, so the
 * conversion happens here rather than scattering `String(...)` through the steps.
 * Without this, revisiting /profile would show a blank form and saving it would
 * overwrite a real profile with empty answers.
 */
export function answersFromProfile(profile: SavedProfile): OnboardingAnswers {
  const saved = new Map(profile.meal_times.map((item) => [item.slot, item]))

  return {
    ...emptyAnswers(),
    sex: profile.sex,
    menstrual_status: profile.menstrual_status ?? null,
    age: String(profile.age),
    weight_kg: String(profile.weight_kg),
    activity: profile.activity,
    goal: profile.goal,
    pace: profile.pace,
    diet_type: profile.diet_type,
    cereal_dominant: profile.cereal_dominant,
    conditions: profile.conditions,
    medications: profile.medications,
    // Carried explicitly. Anything omitted here falls back to emptyAnswers()
    // and is then wiped by the next save, because the PUT replaces rather than
    // merges -- which is how a saved vegetarian-day rule used to disappear.
    observances: profile.observances ?? [],
    avoided: profile.avoided,
    favourites: profile.favourites,
    usual_intake: profile.usual_intake,
    meal_times: SLOT_ORDER.map((slot: MealSlot) => {
      const item = saved.get(slot)
      return {
        slot,
        // Falls back to the default rather than blank, so a profile saved
        // before a slot existed still opens with a usable time.
        time: item?.time ?? DEFAULT_MEAL_TIMES[slot],
        weekend_time: item?.weekend_time ?? null,
        // The saved setting, so a save leaves the Reminders screen's choice as it
        // was; a slot the saved profile has no row for gets a new slot's default.
        reminder_on: item?.reminder_on ?? reminderOnByDefault(slot),
        // Defaults to on for a slot the saved profile has no row for, so a
        // profile written before this field existed still reads as five meals.
        is_enabled: item?.is_enabled ?? true,
      }
    }),
  }
}
