/** How an intake stands against its ICMR-NIN reference figures. */
export type NutrientStatus = 'under' | 'on-target' | 'over' | 'above-limit'

/**
 * Whether the reference figure is something to reach or something to stay below.
 *
 * Almost every nutrient is a `target`. Sodium is the counter-example the spec
 * calls out: its figure is a ceiling inclusive of invisible salt, and a sodium
 * "deficit" is not a thing to compensate — so a low sodium day must not be
 * presented as a shortfall.
 */
export type NutrientKind = 'target' | 'ceiling'

export interface NutrientStanding {
  consumed: number
  /** EAR — the adequacy floor. Null for nutrients ICMR publishes only an AI for. */
  ear: number | null
  /** RDA or AI — the figure shown to the user as today's target. */
  rda: number
  /**
   * Tolerable Upper Limit, or null where ICMR deliberately set none — thiamine,
   * riboflavin, biotin, B12 and potassium. A null TUL must never produce an
   * `above-limit` reading, because the spec forbids raising a food-based surplus
   * warning for those nutrients at all.
   */
  tul: number | null
  kind: NutrientKind
}

export function nutrientStatus({
  consumed,
  ear,
  rda,
  tul,
  kind,
}: NutrientStanding): NutrientStatus {
  // A ceiling nutrient's own figure is the limit, even when no separate TUL exists.
  const limit = kind === 'ceiling' ? (tul ?? rda) : tul

  if (limit !== null && consumed >= limit) return 'above-limit'
  if (kind === 'ceiling') return 'on-target'

  // Without an EAR there is no way to tell a real shortfall from a near miss,
  // so the RDA becomes the floor.
  if (consumed < (ear ?? rda)) return 'under'
  if (consumed > rda) return 'over'
  return 'on-target'
}
