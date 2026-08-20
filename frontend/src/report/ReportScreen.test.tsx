import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { ReportScreen } from './ReportScreen'

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <ReportScreen />
    </QueryClientProvider>,
  )
}

test('shows how much of the week was actually logged', async () => {
  renderScreen()

  expect(await screen.findByText('29 of 35')).toBeInTheDocument()
})

test('lists each nutrient with the days it met its target', async () => {
  renderScreen()

  const row = (await screen.findByText('Calcium')).closest('tr')
  expect(within(row!).getByText('1 of 7')).toBeInTheDocument()
})

/*
 * The report must show what could NOT be made up. Silently dropping an expired
 * shortfall would present a worse week as a better one, which is the exact
 * dishonesty the compensation ledger's `expired` column exists to prevent.
 */
test('reports shortfalls the ledger could not make up, and why', async () => {
  renderScreen()

  expect(await screen.findByText(/1,240 mg/)).toBeInTheDocument()
  expect(await screen.findByText(/30% cap/i)).toBeInTheDocument()
})

test('explains that protein never carries forward', async () => {
  renderScreen()

  expect(await screen.findByText(/no storage pool/i)).toBeInTheDocument()
})

// A week largely eaten out must not be presented with false precision.
test('separates measured intake from estimated intake', async () => {
  renderScreen()

  expect(await screen.findByText(/estimated/i)).toBeInTheDocument()
  expect(await screen.findByText('2,980 kcal')).toBeInTheDocument()
})

test('suggests what to eat next week', async () => {
  renderScreen()

  expect(await screen.findByText(/ragi in place of rice/i)).toBeInTheDocument()
})

/*
 * A chart is unreadable to a screen reader, and Recharts renders SVG with no
 * text alternative. The same series is therefore also exposed as a table.
 */
test('exposes the energy chart’s data as a table for screen readers', async () => {
  renderScreen()

  const table = await screen.findByRole('table', { name: /energy each day/i })
  expect(within(table).getByText('Mon')).toBeInTheDocument()
  expect(within(table).getByText('1,420 kcal')).toBeInTheDocument()
})

test('says plainly that the report is demo data', async () => {
  renderScreen()

  expect(await screen.findByRole('note')).toHaveTextContent(/demo data/i)
})
