/**
 * PROPOSED CONTRACT for `GET /diary?date=` and `POST /diary/entries` —
 * implemented by plan 5.
 */

/** The spec's five slots. Snack 1 is optional and may legitimately be skipped. */
export type MealSlot = 'breakfast' | 'snack1' | 'lunch' | 'snack2' | 'dinner'

export const SLOT_LABELS: Record<MealSlot, string> = {
  breakfast: 'Breakfast',
  snack1: 'Mid-morning snack',
  lunch: 'Lunch',
  snack2: 'Evening snack',
  dinner: 'Dinner',
}

export const SLOT_ORDER: readonly MealSlot[] = [
  'breakfast',
  'snack1',
  'lunch',
  'snack2',
  'dinner',
]

export interface DiaryEntry {
  id: string
  /** Dish or ingredient name as logged. */
  name: string
  /** The household measure as a phrase, e.g. "½ bowl". */
  portion: string
  /** Its two parts, so an entry can be reopened exactly as it was saved. */
  measure_name: string | null
  quantity: number | null
  /** The absolute the nutrients were costed against. */
  grams: number | null
  /**
   * Restaurant and eyeballed portions. The weekly report separates these from
   * measured intake, so a week eaten out is not shown with false precision.
   */
  is_estimated: boolean
  energy_kcal: number
}

export interface DiarySlotState {
  slot: MealSlot
  /** Usual time for this slot from the profile, e.g. "08:00". */
  time: string
  state: 'logged' | 'empty' | 'skipped'
  entries: DiaryEntry[]
}

export interface Diary {
  date: string
  slots: DiarySlotState[]
}

/**
 * Body of `POST /diary/entries`.
 *
 * Either a household measure with a quantity, or an absolute weight. One of the
 * two is required — there is no default weight, because logging a portion the
 * user never described is worse than refusing the entry.
 */
export interface NewDiaryEntry {
  date: string
  slot: MealSlot
  food_id: string
  food_kind: 'dish' | 'ingredient'
  measure_name: string | null
  quantity: number | null
  grams: number | null
  is_estimated: boolean
}
