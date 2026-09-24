/** The canonical storage units from the backend's `nutrients.unit` column. */
export type NutrientUnit = 'kcal' | 'g' | 'mg' | 'ug'

/** µg is stored as the ASCII `ug` but must never be shown that way. */
const UNIT_LABELS: Record<NutrientUnit, string> = {
  kcal: 'kcal',
  g: 'g',
  mg: 'mg',
  ug: 'µg',
}

// en-IN groups as 1,00,000 rather than 100,000.
function grouped(value: number, maximumFractionDigits: number): string {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits }).format(value)
}

/**
 * Render a nutrient amount at a precision that follows the size of the number
 * rather than the name of its unit.
 *
 * Energy is always whole — nobody needs a tenth of a kilocalorie. Everything else
 * keeps one decimal below 10 and rounds above it, because nutrient scales differ
 * by orders of magnitude: B12's whole range is single-digit micrograms, where
 * rounding 2.2 to "2" is a 10% error, while 412.6 µg of folate gains nothing from
 * the ".6".
 */
export function formatAmount(value: number, unit: NutrientUnit): string {
  if (unit === 'kcal') return grouped(Math.round(value), 0)
  if (unit === 'g') return grouped(value, 1)
  return Math.abs(value) < 10 ? grouped(value, 1) : grouped(Math.round(value), 0)
}

export function unitLabel(unit: NutrientUnit): string {
  return UNIT_LABELS[unit]
}

/** `410 mg` — an amount with its unit, for prose and screen-reader labels. */
export function formatWithUnit(value: number, unit: NutrientUnit): string {
  return `${formatAmount(value, unit)} ${unitLabel(unit)}`
}

export function formatPercent(consumed: number, target: number): number {
  if (!target) return 0
  return Math.round((consumed / target) * 100)
}

/**
 * `3 Aug 2026` from an ISO calendar date.
 *
 * Built from its parts rather than parsed, because `new Date('2026-08-01')` is
 * UTC midnight — which is still 31 July anywhere west of Greenwich.
 */
export function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(year, month - 1, day))
}
