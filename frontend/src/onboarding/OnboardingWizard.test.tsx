import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { OnboardingWizard } from './OnboardingWizard'

// 404 is the backend's "not onboarded yet" answer, which is the state these
// tests exercise: a fresh user filling the questionnaire in for the first time.
beforeEach(() => {
  server.use(
    http.get(apiUrl('/profile'), () => new HttpResponse('no profile', { status: 404 })),
  )
})

async function renderWizard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OnboardingWizard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  // The wizard waits for the saved profile before it can prefill.
  await screen.findByRole('heading', { name: 'About you' })
}

test('starts on the first step', async () => {
  await renderWizard()

  expect(screen.getByRole('heading', { name: 'About you' })).toBeInTheDocument()
  expect(screen.getByText('Step 1 of 8')).toBeInTheDocument()
})

// Advancing past an invalid step would produce silently wrong targets rather
// than an obvious failure, because energy is computed from these figures.
test('will not advance while the step is incomplete', async () => {
  await renderWizard()

  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

  expect(screen.getByRole('alert')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'About you' })).toBeInTheDocument()
})

test('advances once the step is filled in', async () => {
  await renderWizard()

  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'male')
  await userEvent.type(screen.getByLabelText('Age'), '34')
  await userEvent.type(screen.getByLabelText(/weight in kg/i), '74.2')
  await userEvent.selectOptions(screen.getByLabelText(/activity level/i), 'moderate')
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

  expect(screen.getByRole('heading', { name: 'Your goal' })).toBeInTheDocument()
})

test('the error clears as soon as the user starts fixing it', async () => {
  await renderWizard()

  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(screen.getByRole('alert')).toBeInTheDocument()

  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'female')

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// Height is deliberately not collected: the ICMR energy equations are
// weight-based, and the spec found reference heights unverifiable.
test('never asks for height', async () => {
  await renderWizard()

  expect(screen.queryByLabelText(/height/i)).not.toBeInTheDocument()
})

test('cannot go back from the first step', async () => {
  await renderWizard()

  expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()
})

async function goToConditions() {
  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'male')
  await userEvent.type(screen.getByLabelText('Age'), '34')
  await userEvent.type(screen.getByLabelText(/weight in kg/i), '74.2')
  await userEvent.selectOptions(screen.getByLabelText(/activity level/i), 'moderate')
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

  await userEvent.selectOptions(screen.getByLabelText(/aiming for/i), 'maintain')
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

  await userEvent.selectOptions(screen.getByLabelText(/how do you eat/i), 'vegetarian')
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
}

/*
 * Hypertension and symptomatic hypotension give opposite sodium instructions.
 * The spec requires the conflict to be surfaced for clinician review, never
 * averaged into a single number.
 */
test('flags two conditions that give opposite advice', async () => {
  await renderWizard()
  await goToConditions()

  await userEvent.click(screen.getByRole('checkbox', { name: /high blood pressure/i }))
  await userEvent.click(screen.getByRole('checkbox', { name: /low blood pressure/i }))

  expect(screen.getByRole('alert')).toHaveTextContent(/will not average them/i)
})

test('does not flag an ordinary combination of conditions', async () => {
  await renderWizard()
  await goToConditions()

  await userEvent.click(screen.getByRole('checkbox', { name: /type 2 diabetes/i }))
  await userEvent.click(screen.getByRole('checkbox', { name: /high cholesterol/i }))

  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

// The dose time is what the planner checks breakfast against for the 60-minute
// levothyroxine window, so a half-filled medication must not pass.
test('will not advance with a medication that has no dose time', async () => {
  await renderWizard()
  await goToConditions()

  await userEvent.click(screen.getByRole('button', { name: /add a medication/i }))
  await userEvent.type(screen.getByLabelText('Medication 1 name'), 'Levothyroxine')
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }))

  expect(screen.getByRole('alert')).toHaveTextContent(/time you take it/i)
})

test('asks about periods only once Female is chosen', async () => {
  await renderWizard()

  expect(screen.queryByLabelText(/still have periods/i)).not.toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'female')
  expect(screen.getByLabelText(/still have periods/i)).toBeInTheDocument()

  await userEvent.selectOptions(screen.getByLabelText('Sex'), 'male')
  expect(screen.queryByLabelText(/still have periods/i)).not.toBeInTheDocument()
})
