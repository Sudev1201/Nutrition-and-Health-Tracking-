import type { CookingView, PlanDay, WeekPlan } from '../../plan/types'

/**
 * A Sunday-to-Saturday week with the constraints that make the planner
 * interesting: a recurring Friday vegetarian rule, a locked meal that must
 * survive regeneration, and breakfast pushed clear of the levothyroxine window.
 *
 * `/plan/week` and `/plan/cooking` are real endpoints now (plan 6). This fixture
 * is kept for `PlanScreen.test.tsx`, which stubs them per test: a generated plan
 * would not reliably produce a locked meal or a rationale to assert against.
 */
function day(
  date: string,
  weekday: string,
  dishes: [string, string, string][],
  options: { vegetarian?: boolean; reason?: string; lockedIndex?: number } = {},
): PlanDay {
  const slots = ['breakfast', 'snack1', 'lunch', 'snack2', 'dinner'] as const

  return {
    date,
    weekday,
    vegetarian: options.vegetarian ?? false,
    vegetarian_reason: options.reason ?? null,
    items: dishes.map(([name, portion, rationale], index) => ({
      id: `${date}-${slots[index]}`,
      slot: slots[index],
      dish_id: `dish-${name.toLowerCase().replace(/\s+/g, '-')}`,
      dish_name: name,
      portion,
      locked: options.lockedIndex === index,
      rationale: rationale === '' ? null : rationale,
    })),
  }
}

export const PLAN_FIXTURE: WeekPlan = {
  start_date: '2026-08-16',
  days: [
    day('2026-08-16', 'Sunday', [
      ['Ven pongal', '1.5 cup', 'Closes the morning protein gap with moong dal'],
      ['Filter coffee', '1 tumbler', 'Scheduled 60 min after levothyroxine'],
      ['Rice with sambar', '2 cup', ''],
      ['Sundal', '1 katori', 'Legume, holds the cereal:legume ratio up'],
      ['Chapati with kootu', '3 pieces', ''],
    ]),
    day('2026-08-17', 'Monday', [
      ['Idli with sambar', '3 idli', 'Pairs idli with dal for protein'],
      ['Buttermilk', '1 glass', ''],
      ['Curd rice with poriyal', '1.5 cup', ''],
      ['Sundal', '1 katori', ''],
      ['Ragi dosa', '2 pieces', 'Ragi carries 364 mg calcium per 100 g'],
    ], { lockedIndex: 2 }),
    day('2026-08-18', 'Tuesday', [
      ['Adai with avial', '2 pieces', 'Mixed dal adai is the week’s protein peak'],
      ['Tea', '1 cup', 'Kept 1 h from the iron-rich lunch'],
      ['Rice with fish curry', '2 cup', ''],
      ['Groundnut sundal', '1 katori', ''],
      ['Dosa with chutney', '3 pieces', ''],
    ]),
    day('2026-08-19', 'Wednesday', [
      ['Upma', '1 cup', ''],
      ['Filter coffee', '1 tumbler', ''],
      ['Rice with rasam and beans poriyal', '2 cup', ''],
      ['Sundal', '1 katori', ''],
      ['Idiyappam with kurma', '3 pieces', ''],
    ]),
    day('2026-08-20', 'Thursday', [
      ['Pesarattu', '2 pieces', ''],
      ['Tea', '1 cup', ''],
      ['Rice with chicken curry', '2 cup', 'B12 top-up before Friday'],
      ['Boiled corn', '1 katori', ''],
      ['Chapati with dal', '3 pieces', ''],
    ]),
    day(
      '2026-08-21',
      'Friday',
      [
        ['Idli with sambar', '3 idli', ''],
        ['Filter coffee', '1 tumbler', ''],
        ['Rice with vatha kuzhambu', '2 cup', ''],
        ['Sundal', '1 katori', 'Legume protein, no egg today'],
        ['Ragi kanji', '1 glass', 'Calcium, and gentle before bed'],
      ],
      { vegetarian: true, reason: 'your Friday rule' },
    ),
    day('2026-08-22', 'Saturday', [
      ['Poori with potato masala', '3 pieces', ''],
      ['Tea', '1 cup', ''],
      ['Biryani', '1.5 cup', ''],
      ['Fruit', '1 katori', ''],
      ['Rava dosa', '2 pieces', ''],
    ]),
  ],
}

export const COOKING_FIXTURE: CookingView = {
  date: '2026-08-17',
  overlaps: [
    { slot: 'breakfast', dish_name: 'Idli with sambar', members: ['Sudev', 'Amma'] },
    // Ordered so the joined text does not contain "Sudev, Amma" as a substring —
    // that would collide with the breakfast overlap under a loose text match.
    { slot: 'dinner', dish_name: 'Ragi dosa', members: ['Amma', 'Sudev', 'Appa'] },
  ],
}
