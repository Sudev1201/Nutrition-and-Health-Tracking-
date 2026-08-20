/**
 * The meal list, and the three states a slot can be in.
 *
 * `skipped` is not `empty`: empty means the app does not know what happened,
 * skipped means the user said nothing was eaten there.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import type { Diary, DiarySlotState, MealSlot } from '../log/types'
import { MealSlotList } from './MealSlotList'

function slot(overrides: Partial<DiarySlotState> = {}): DiarySlotState {
  return { slot: 'snack1', time: '11:00', state: 'empty', entries: [], ...overrides }
}

function diary(slots: DiarySlotState[]): Diary {
  return { date: '2026-08-20', slots }
}

function renderList(value: Diary) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MealSlotList diary={value} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('a skipped slot says so', () => {
  renderList(diary([slot({ state: 'skipped' })]))

  expect(screen.getByText(/skipped/i)).toBeInTheDocument()
})

test('the skipped copy does not claim every slot is the mid-morning snack', () => {
  renderList(diary([slot({ slot: 'dinner', state: 'skipped' })]))

  expect(screen.getByText(/skipped/i)).toBeInTheDocument()
  expect(screen.queryByText(/mid-morning snack is optional/i)).not.toBeInTheDocument()
})

test('an empty slot offers a way to skip it', () => {
  renderList(diary([slot({ slot: 'lunch' })]))

  expect(screen.getByRole('button', { name: /skip lunch/i })).toBeInTheDocument()
})

test('a main meal can be skipped too, not just the snacks', () => {
  renderList(diary([slot({ slot: 'breakfast' }), slot({ slot: 'dinner' })]))

  expect(screen.getByRole('button', { name: /skip breakfast/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /skip dinner/i })).toBeInTheDocument()
})

test('a logged slot offers no skip button', () => {
  renderList(
    diary([
      slot({
        slot: 'lunch',
        state: 'logged',
        entries: [
          {
            id: '1',
            name: 'Sambar',
            portion: '1 bowl',
            measure_name: 'bowl',
            quantity: 1,
            grams: 200,
            is_estimated: false,
            energy_kcal: 180,
          },
        ],
      }),
    ]),
  )

  expect(screen.queryByRole('button', { name: /skip/i })).not.toBeInTheDocument()
})

test('skipping a slot posts it to the diary', async () => {
  let posted: { date: string; slot: MealSlot } | null = null
  server.use(
    http.post(apiUrl('/diary/skips'), async ({ request }) => {
      posted = (await request.json()) as { date: string; slot: MealSlot }
      return HttpResponse.json({ slot: posted.slot, state: 'skipped' }, { status: 201 })
    }),
  )

  renderList(diary([slot({ slot: 'lunch' })]))
  await userEvent.click(screen.getByRole('button', { name: /skip lunch/i }))

  expect(posted).toEqual({ date: '2026-08-20', slot: 'lunch' })
})

test('a skipped slot can be undone', async () => {
  let deleted = false
  server.use(
    http.delete(apiUrl('/diary/skips'), () => {
      deleted = true
      return new HttpResponse(null, { status: 204 })
    }),
  )

  renderList(diary([slot({ slot: 'lunch', state: 'skipped' })]))
  await userEvent.click(screen.getByRole('button', { name: /log it after all/i }))

  expect(deleted).toBe(true)
})
