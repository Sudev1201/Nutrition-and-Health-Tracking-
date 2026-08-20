import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { NutrientBar } from './NutrientBar'

const CALCIUM = {
  name: 'Calcium',
  unit: 'mg',
  ear: 800,
  tul: 2500,
  kind: 'target',
} as const

test('shows what was consumed against today’s target', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  expect(screen.getByText('410 / 1,000 mg')).toBeInTheDocument()
})

test('shows the share of the target reached', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  expect(screen.getByText('41%')).toBeInTheDocument()
})

// Roughly 1 in 12 men has a red-green colour deficiency, and these bars are also
// read in screenshots and printouts. The status must survive without the colour.
test('states the status in words so colour is never the only signal', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  expect(screen.getByText('under target')).toBeInTheDocument()
})

test('calls out an intake that has reached the upper limit', () => {
  render(<NutrientBar {...CALCIUM} consumed={2600} target={1000} />)

  expect(screen.getByText('past the upper limit')).toBeInTheDocument()
})

test('names the day a carried-forward adjustment came from', () => {
  render(
    <NutrientBar {...CALCIUM} consumed={410} target={1180} carriedIn={180} carriedFrom="Friday" />,
  )

  expect(screen.getByText('+180 mg carried from Friday')).toBeInTheDocument()
})

test('shows no carry annotation when the ledger contributed nothing', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  expect(screen.queryByText(/carried/i)).not.toBeInTheDocument()
})

test('exposes progressbar semantics naming the nutrient', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  const bar = screen.getByRole('progressbar', { name: /calcium/i })
  expect(bar).toHaveAttribute('aria-valuenow', '410')
  expect(bar).toHaveAttribute('aria-valuemax', '1000')
})

// The track spans 0 to today's target, so a ceiling 2.5x the target sits off the
// end of it. Drawing that tick on every ordinary row would be noise; it earns its
// place only once the intake is actually in range of the limit.
test('marks where the upper limit falls once intake reaches it', () => {
  render(<NutrientBar {...CALCIUM} consumed={2600} target={1000} />)

  expect(screen.getByTitle('Upper limit 2,500 mg')).toBeInTheDocument()
})

test('draws no limit marker on an ordinary day far below the ceiling', () => {
  render(<NutrientBar {...CALCIUM} consumed={410} target={1000} />)

  expect(screen.queryByTitle(/upper limit/i)).not.toBeInTheDocument()
})

// Once the bar has to stretch past today's target to fit the intake, the target
// itself needs a tick or you cannot see what was overshot.
test('marks where the target fell once intake has overshot it', () => {
  render(<NutrientBar {...CALCIUM} consumed={2600} target={1000} />)

  expect(screen.getByTitle('Target 1,000 mg')).toBeInTheDocument()
})

// ICMR deliberately set no upper limit for B12, so there is no ceiling to draw.
test('draws no limit marker for a nutrient ICMR set no limit for', () => {
  render(
    <NutrientBar name="Vitamin B12" unit="ug" ear={2} tul={null} kind="target" consumed={1} target={2.2} />,
  )

  expect(screen.queryByTitle(/upper limit/i)).not.toBeInTheDocument()
})
