import { expect, test } from 'vitest'
import { formatAmount, formatPercent, formatWithUnit, unitLabel } from './format'

test('energy is rounded to whole kcal', () => {
  expect(formatAmount(2110.4, 'kcal')).toBe('2,110')
})

// The app is for Indian users, so grouping is 1,00,000 rather than 100,000.
test('large figures group the Indian way', () => {
  expect(formatAmount(100000, 'kcal')).toBe('1,00,000')
})

test('grams keep one decimal when there is a fraction', () => {
  expect(formatAmount(54.55, 'g')).toBe('54.6')
})

test('grams drop a trailing zero decimal', () => {
  expect(formatAmount(54, 'g')).toBe('54')
})

test('milligrams are whole numbers at everyday magnitudes', () => {
  expect(formatAmount(1000.4, 'mg')).toBe('1,000')
})

/*
 * Rounding every microgram figure to a whole number rendered B12's 2.2 µg RDA as
 * "2 µg" and a 7.5 µg intake as "8 µg" -- a display error of over 30% on a
 * nutrient whose entire scale is single digits. Precision has to follow the
 * magnitude of the number, not the name of its unit.
 */
test('single-digit micrograms keep a decimal', () => {
  expect(formatAmount(2.2, 'ug')).toBe('2.2')
})

test('single-digit milligrams keep a decimal', () => {
  expect(formatAmount(9.4, 'mg')).toBe('9.4')
})

test('micrograms in the tens and above are whole numbers', () => {
  expect(formatAmount(412.6, 'ug')).toBe('413')
})

test('a percentage of target is a rounded whole number', () => {
  expect(formatPercent(410, 1000)).toBe(41)
})

// A zero target would make this Infinity and render as "Infinity%".
test('a zero target yields zero percent rather than infinity', () => {
  expect(formatPercent(410, 0)).toBe(0)
})

// The backend stores micrograms as the ASCII "ug" because the column is 8 chars
// of plain SQL. Showing "410 ug" to a user would be wrong.
test('micrograms display as µg, never as the stored ascii ug', () => {
  expect(unitLabel('ug')).toBe('µg')
})

test('units that need no translation pass through', () => {
  expect(unitLabel('kcal')).toBe('kcal')
})

test('an amount can be rendered with its unit for prose and screen readers', () => {
  expect(formatWithUnit(410, 'mg')).toBe('410 mg')
})
