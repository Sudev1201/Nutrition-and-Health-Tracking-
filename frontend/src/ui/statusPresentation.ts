import type { NutrientStatus } from '../lib/status'

/**
 * How a nutrient status is spelled and coloured. Kept out of `lib/status.ts`,
 * which is pure domain logic, and shared by every component that shows a status
 * so the wording cannot drift between the tiles and the bars.
 *
 * The label always accompanies the colour — status must never be conveyed by
 * colour alone.
 */
export const STATUS_LABELS: Record<NutrientStatus, string> = {
  under: 'under target',
  'on-target': 'on target',
  over: 'over target',
  'above-limit': 'past the upper limit',
}

export const STATUS_TEXT: Record<NutrientStatus, string> = {
  under: 'text-under',
  'on-target': 'text-on-target',
  over: 'text-over',
  'above-limit': 'text-above-limit',
}

export const STATUS_FILL: Record<NutrientStatus, string> = {
  under: 'bg-under',
  'on-target': 'bg-on-target',
  over: 'bg-over',
  'above-limit': 'bg-above-limit',
}
