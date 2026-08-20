import { expect, test } from 'vitest'
import { nutrientStatus } from './status'

// A target nutrient: shortfall below EAR is real, surplus past the TUL is an alarm.
const CALCIUM = { ear: 800, rda: 1000, tul: 2500, kind: 'target' } as const

test('below the EAR floor is a real shortfall', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 410 })).toBe('under')
})

test('exactly at the EAR floor is no longer a shortfall', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 800 })).toBe('on-target')
})

test('between the EAR floor and the RDA is on target', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 900 })).toBe('on-target')
})

test('exactly at the RDA is on target, not over', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 1000 })).toBe('on-target')
})

test('above the RDA but under the upper limit is over', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 1400 })).toBe('over')
})

test('exactly at the upper limit is already past it', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 2500 })).toBe('above-limit')
})

test('above the upper limit is an alarm', () => {
  expect(nutrientStatus({ ...CALCIUM, consumed: 3000 })).toBe('above-limit')
})

// ICMR deliberately set no upper limit for thiamine, riboflavin, biotin, B12 or
// potassium. The spec is explicit that no food-based surplus warning may be
// raised for those, so a null TUL must never reach 'above-limit'.
test('a nutrient with no upper limit never reaches above-limit, however high', () => {
  expect(
    nutrientStatus({ ear: 1.6, rda: 2, tul: null, kind: 'target', consumed: 500 }),
  ).toBe('over')
})

test('a nutrient with no EAR falls back to the RDA to decide a shortfall', () => {
  expect(
    nutrientStatus({ ear: null, rda: 30, tul: null, kind: 'target', consumed: 12 }),
  ).toBe('under')
})

// Sodium is a ceiling, not a target: the spec says a sodium "deficit" is not a
// thing to compensate, so a low intake must read as fine rather than amber.
const SODIUM = { ear: null, rda: 2000, tul: 2000, kind: 'ceiling' } as const

test('a ceiling nutrient well under its limit is on target, never under', () => {
  expect(nutrientStatus({ ...SODIUM, consumed: 400 })).toBe('on-target')
})

test('a ceiling nutrient just under its limit is still on target', () => {
  expect(nutrientStatus({ ...SODIUM, consumed: 1999 })).toBe('on-target')
})

test('a ceiling nutrient at its limit is past it', () => {
  expect(nutrientStatus({ ...SODIUM, consumed: 2000 })).toBe('above-limit')
})
