import { expect, test } from 'vitest'
import { cx } from './cx'

test('joins the class names it is given', () => {
  expect(cx('rounded', 'border')).toBe('rounded border')
})

// Conditional classes are the whole point: `cx('a', isActive && 'b')` must not
// leak `false` into the class attribute.
test('drops falsy entries rather than stringifying them', () => {
  expect(cx('rounded', false, undefined, null, '', 'border')).toBe('rounded border')
})

test('returns an empty string when nothing survives', () => {
  expect(cx(false, undefined)).toBe('')
})
