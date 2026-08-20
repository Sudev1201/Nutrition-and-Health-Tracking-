/**
 * The profile summary.
 *
 * `/profile` used to render the onboarding questionnaire itself, which meant
 * there was no way to read your answers back without being put in front of an
 * eight-step form. This screen shows them, and sends you into the wizard at the
 * one section you want to change.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { ProfileScreen } from './ProfileScreen'

const PROFILE = {
  sex: 'female',
  age: 34,
  weight_kg: 58.5,
  activity: 'moderate',
  goal: 'lose',
  pace: 'gentle',
  diet_type: 'eggetarian',
  cereal_dominant: true,
  conditions: ['hypothyroidism'],
  medications: [{ name: 'Levothyroxine', time: '06:30' }],
  meal_times: [
    { slot: 'breakfast', time: '08:00', weekend_time: '09:30', reminder_on: true, is_enabled: true },
    { slot: 'snack1', time: '11:00', weekend_time: null, reminder_on: false, is_enabled: false },
    { slot: 'lunch', time: '13:30', weekend_time: null, reminder_on: true, is_enabled: true },
    { slot: 'snack2', time: '17:00', weekend_time: null, reminder_on: true, is_enabled: true },
    { slot: 'dinner', time: '20:30', weekend_time: null, reminder_on: true, is_enabled: true },
  ],
  observances: [
    { kind: 'weekday', weekday: 2, start_date: null, end_date: null, label: 'No meat on Tuesdays' },
  ],
  avoided: [{ label: 'Peanut', food_id: null, food_kind: null }],
  favourites: [{ label: 'Curd', food_id: null, food_kind: null }],
  usual_intake: [
    { slot: 'breakfast', label: 'Idli', food_id: 'a', food_kind: 'dish', grams: 150 },
  ],
}

function stub(body: typeof PROFILE | null = PROFILE, status = 200) {
  server.use(
    http.get(apiUrl('/profile'), () =>
      status === 200 ? HttpResponse.json(body) : new HttpResponse(null, { status }),
    ),
  )
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProfileScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => stub())

test('every section of the questionnaire gets a heading', async () => {
  renderScreen()

  for (const title of [
    'About you',
    'Your goal',
    'How you eat',
    'Health conditions',
    'Vegetarian days',
    'Foods you like and avoid',
    'When you eat',
    'What you usually eat',
  ]) {
    expect(await screen.findByRole('region', { name: title })).toBeInTheDocument()
  }
})

test('the answers are shown as words, not raw codes', async () => {
  renderScreen()

  expect(await screen.findByText('Female')).toBeInTheDocument()
  expect(screen.getByText('Moderate')).toBeInTheDocument()
  expect(screen.getByText('Lose weight')).toBeInTheDocument()
  expect(screen.getByText('Vegetarian, plus egg')).toBeInTheDocument()
  // Not the wire value.
  expect(screen.queryByText('eggetarian')).not.toBeInTheDocument()
})

test('a condition reads as its label rather than its code', async () => {
  renderScreen()

  expect(await screen.findByText(/thyroid/i)).toBeInTheDocument()
  expect(screen.queryByText('hypothyroidism')).not.toBeInTheDocument()
})

test('each section offers a way to edit just that section', async () => {
  renderScreen()

  const link = await screen.findByRole('link', { name: /edit about you/i })
  expect(link).toHaveAttribute('href', '/profile/about')
})

test('a disabled snack is shown as not part of the day', async () => {
  renderScreen()

  const section = await screen.findByRole('region', { name: 'When you eat' })
  expect(section).toHaveTextContent(/mid-morning snack/i)
  expect(section).toHaveTextContent(/not part of your day/i)
})

test('an observance is listed', async () => {
  renderScreen()

  expect(await screen.findByText('No meat on Tuesdays')).toBeInTheDocument()
})

test('conflicting conditions are called out', async () => {
  stub({ ...PROFILE, conditions: ['hypertension', 'hypotension'] })
  renderScreen()

  expect(await screen.findByRole('alert')).toBeInTheDocument()
})

test('someone who has not onboarded is sent to the questionnaire, not shown blanks', async () => {
  stub(null, 404)
  renderScreen()

  const link = await screen.findByRole('link', { name: /set up your profile/i })
  expect(link).toHaveAttribute('href', '/profile/about')
})

test('a real failure says so rather than rendering an empty profile', async () => {
  stub(null, 500)
  renderScreen()

  expect(await screen.findByRole('alert')).toBeInTheDocument()
})
