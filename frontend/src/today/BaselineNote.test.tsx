/**
 * The baseline card. Its job is to show the gap between what someone eats now
 * and what they need, so a first-week plan is a step rather than a jump.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { BaselineNote } from './BaselineNote'

function nutrient(overrides: Record<string, unknown>) {
  return {
    code: 'calcium',
    display_name: 'Calcium',
    unit: 'mg',
    category: 'mineral',
    kind: 'target',
    ear: 800,
    rda: 1000,
    tul: 2500,
    usual: 180,
    off_target: true,
    ...overrides,
  }
}

const BASELINE = {
  has_usual_intake: true,
  usual_energy_kcal: 1850,
  target_energy_kcal: 2110,
  difference_kcal: -260,
  implausible: false,
  note: null,
  nutrients: [] as ReturnType<typeof nutrient>[],
}

function stub(overrides: Partial<typeof BASELINE> = {}) {
  server.use(
    http.get(apiUrl('/profile/baseline'), () =>
      HttpResponse.json({ ...BASELINE, ...overrides }),
    ),
  )
}

function renderNote() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BaselineNote date="2026-08-20" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => stub())

test('the energy summary still reads as it did', async () => {
  renderNote()

  expect(await screen.findByText(/1,850/)).toBeInTheDocument()
  expect(screen.getByText(/260/)).toBeInTheDocument()
})

test('a nutrient a usual day falls short on is named', async () => {
  stub({ nutrients: [nutrient({})] })
  renderNote()

  expect(await screen.findByText('Calcium')).toBeInTheDocument()
  expect(screen.getByText(/180/)).toBeInTheDocument()
})

test('a nutrient that is on target is not listed', async () => {
  stub({
    nutrients: [
      nutrient({}),
      nutrient({ code: 'protein', display_name: 'Protein', off_target: false }),
    ],
  })
  renderNote()

  expect(await screen.findByText('Calcium')).toBeInTheDocument()
  expect(screen.queryByText('Protein')).not.toBeInTheDocument()
})

test('energy is not repeated in the shortfall list', async () => {
  stub({
    nutrients: [
      nutrient({ code: 'energy', display_name: 'Energy', unit: 'kcal' }),
      nutrient({}),
    ],
  })
  renderNote()

  await screen.findByText('Calcium')
  expect(screen.queryByText('Energy')).not.toBeInTheDocument()
})

test('a ceiling nutrient over its limit reads as too much, not too little', async () => {
  stub({
    nutrients: [
      nutrient({
        code: 'sodium',
        display_name: 'Sodium',
        kind: 'ceiling',
        ear: null,
        rda: 2000,
        tul: null,
        usual: 3200,
        off_target: true,
      }),
    ],
  })
  renderNote()

  expect(await screen.findByText('Sodium')).toBeInTheDocument()
  expect(screen.getByText(/too much/i)).toBeInTheDocument()
})

test('nothing off target means no shortfall list at all', async () => {
  stub({ nutrients: [nutrient({ off_target: false })] })
  renderNote()

  await screen.findByText(/1,850/)
  expect(screen.queryByText(/how a usual day compares/i)).not.toBeInTheDocument()
})
