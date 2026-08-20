/** One household measure a food can be logged in. */
export interface Measure {
  name: string
  grams: number
  is_default: boolean
  /** A general weight rather than one measured for this food. */
  is_approximate: boolean
  /** `ml` for drinking vessels, `g` otherwise. */
  unit: string
}

/** A portion in both units at once. */
export interface Portion {
  measure_name: string | null
  quantity: number | null
  grams: number | null
}

export const EMPTY_PORTION: Portion = { measure_name: null, quantity: null, grams: null }

/*
 * The quantities people actually say. "Half a cup" and "one and a half bowls"
 * are how a portion gets described at the table; 0.5 and 1.5 are not.
 */
export const QUANTITIES: { value: number; label: string }[] = [
  { value: 0.25, label: '¼' },
  { value: 0.5, label: '½' },
  { value: 0.75, label: '¾' },
  { value: 1, label: '1' },
  { value: 1.5, label: '1½' },
  { value: 2, label: '2' },
  { value: 2.5, label: '2½' },
  { value: 3, label: '3' },
  { value: 4, label: '4' },
]

export function quantityLabel(quantity: number | null): string {
  if (quantity === null) return ''
  return QUANTITIES.find((option) => option.value === quantity)?.label ?? String(quantity)
}
