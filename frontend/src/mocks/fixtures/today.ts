import type { TodayTargets } from '../../today/types'

/**
 * A deliberately awkward day, not a happy path. It carries every state the Today
 * screen has to render correctly:
 *
 *  - calcium short, with 180 mg carried in from Friday's shortfall
 *  - sodium past its ceiling (pickle and appalam), which is an alarm not a "win"
 *  - protein short with NO carry, because protein has no storage pool
 *  - B12 far over its RDA but with no upper limit, so no warning may be raised
 *  - a hypertension + hypotension conflict flagged rather than averaged
 *  - a levothyroxine timing note
 *
 * Figures are plausible ICMR-NIN reference values for an adult man, but they are
 * fixtures — the screen carries a DemoDataBanner saying so.
 */
export const TODAY_FIXTURE: TodayTargets = {
  date: '2026-08-17',
  nutrients: [
    {
      code: 'energy',
      display_name: 'Energy',
      unit: 'kcal',
      category: 'macro',
      kind: 'target',
      ear: null,
      rda: 2110,
      tul: null,
      target_effective: 2110,
      carried_in: 0,
      carried_from: null,
      consumed: 1420,
    },
    {
      // No carry, ever: a 12-day trial found no catch-up for insufficient amino
      // acid intake, so a protein deficit expires at midnight.
      code: 'protein',
      display_name: 'Protein',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      ear: 43,
      rda: 54,
      tul: null,
      target_effective: 54,
      carried_in: 0,
      carried_from: null,
      consumed: 38,
    },
    {
      code: 'fibre',
      display_name: 'Fibre',
      unit: 'g',
      category: 'macro',
      kind: 'target',
      ear: null,
      rda: 32,
      tul: null,
      // Fibre's carry is capped at 25% of the daily target, because doubling
      // fibre in a day causes GI distress.
      target_effective: 36,
      carried_in: 4,
      carried_from: 'Friday',
      consumed: 21,
    },
    {
      code: 'calcium',
      display_name: 'Calcium',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      ear: 800,
      rda: 1000,
      tul: 2500,
      target_effective: 1180,
      carried_in: 180,
      carried_from: 'Friday',
      consumed: 410,
    },
    {
      code: 'iron',
      display_name: 'Iron',
      unit: 'mg',
      category: 'mineral',
      kind: 'target',
      ear: 13,
      rda: 19,
      tul: 45,
      target_effective: 19,
      carried_in: 0,
      carried_from: null,
      consumed: 12,
    },
    {
      // A ceiling, not a target. Under it is fine; a "deficit" is meaningless.
      code: 'sodium',
      display_name: 'Sodium',
      unit: 'mg',
      category: 'mineral',
      kind: 'ceiling',
      ear: null,
      rda: 2000,
      tul: 2000,
      target_effective: 2000,
      carried_in: 0,
      carried_from: null,
      consumed: 2680,
    },
    {
      // ICMR set no upper limit for B12, so 340% of the RDA must raise nothing.
      code: 'vitamin_b12',
      display_name: 'Vitamin B12',
      unit: 'ug',
      category: 'vitamin',
      kind: 'target',
      ear: 2,
      rda: 2.2,
      tul: null,
      target_effective: 2.2,
      carried_in: 0,
      carried_from: null,
      consumed: 7.5,
    },
    {
      code: 'vitamin_c',
      display_name: 'Vitamin C',
      unit: 'mg',
      category: 'vitamin',
      kind: 'target',
      ear: 65,
      rda: 80,
      tul: 2000,
      target_effective: 80,
      carried_in: 0,
      carried_from: null,
      consumed: 96,
    },
  ],
  warnings: [
    {
      kind: 'condition-conflict',
      message:
        'Your profile lists both hypertension and symptomatic hypotension, which give opposite sodium advice. Targets have not been averaged — please discuss this with your clinician.',
    },
    {
      kind: 'medication-timing',
      message:
        'Levothyroxine at 07:00 means the first food or drink of the day — including milk coffee — should wait until 08:00.',
    },
  ],
}
