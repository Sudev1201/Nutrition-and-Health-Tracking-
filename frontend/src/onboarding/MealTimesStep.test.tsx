/**
 * The "When you eat" step.
 *
 * Not everyone eats five times a day. Turning a snack off is a standing
 * preference about the shape of a normal day — a different statement from
 * skipping a meal on one particular date, which lives on the Today screen.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { MealTimesStep } from './steps'
import type { OnboardingAnswers } from './types'
import { emptyAnswers } from './validation'

function renderStep(overrides: Partial<OnboardingAnswers> = {}) {
  const update = vi.fn()
  const answers = { ...emptyAnswers(), ...overrides }
  render(<MealTimesStep answers={answers} update={update} />)
  return { update, answers }
}

test('every slot starts enabled, so the default day has five meals', () => {
  const { answers } = renderStep()

  expect(answers.meal_times.every((meal) => meal.is_enabled)).toBe(true)
})

test('the optional snacks can be switched off', () => {
  renderStep()

  expect(screen.getByRole('switch', { name: /mid-morning snack/i })).toBeInTheDocument()
  expect(screen.getByRole('switch', { name: /evening snack/i })).toBeInTheDocument()
})

test('the main meals offer no switch', () => {
  renderStep()

  expect(screen.queryByRole('switch', { name: /breakfast/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('switch', { name: /lunch/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('switch', { name: /dinner/i })).not.toBeInTheDocument()
})

test('switching a snack off records it', async () => {
  const { update } = renderStep()

  await userEvent.click(screen.getByRole('switch', { name: /mid-morning snack/i }))

  const patch = update.mock.calls[0][0] as Partial<OnboardingAnswers>
  const snack1 = patch.meal_times?.find((meal) => meal.slot === 'snack1')
  expect(snack1?.is_enabled).toBe(false)
})

test('a disabled snack hides its time inputs, since it has no time', () => {
  renderStep({
    meal_times: emptyAnswers().meal_times.map((meal) =>
      meal.slot === 'snack1' ? { ...meal, is_enabled: false } : meal,
    ),
  })

  expect(
    screen.queryByLabelText(/mid-morning snack time/i),
  ).not.toBeInTheDocument()
  expect(screen.getByLabelText(/lunch time/i)).toBeInTheDocument()
})
