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

// --- an unmeasured nutrient ---------------------------------------------------
//
// A nutrient no food that day carried a figure for has `coverage: 0`, and its
// `consumed` is silence rather than zero. Drawing an empty bar would state that
// the user ate none of it, which is a claim the data does not support.

test('a nutrient nothing measured says so instead of showing an empty bar', () => {
  render(
    <NutrientBar
      name="Iodine"
      unit="ug"
      consumed={0}
      target={150}
      ear={null}
      tul={900}
      kind="target"
      coverage={0}
    />,
  )

  expect(screen.getByText(/not measured/i)).toBeInTheDocument()
})

test('a partly measured nutrient says how much of the day it speaks for', () => {
  render(
    <NutrientBar
      name="Iodine"
      unit="ug"
      consumed={150}
      target={150}
      ear={null}
      tul={900}
      kind="target"
      coverage={0.02}
    />,
  )

  expect(screen.getByText(/2% of what you ate/i)).toBeInTheDocument()
})

test('a fully measured nutrient carries no caveat', () => {
  render(
    <NutrientBar
      name="Calcium"
      unit="mg"
      consumed={800}
      target={1000}
      ear={800}
      tul={2500}
      kind="target"
      coverage={1}
    />,
  )

  expect(screen.queryByText(/not measured/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/of what you ate/i)).not.toBeInTheDocument()
})

// --- a lowered target -----------------------------------------------------------
//
// A harmful surplus lowers the next two days: a 4,000 mg sodium Sunday takes
// 600 mg off each of Monday's and Tuesday's 2,000 mg ceilings. A ceiling that
// drops overnight with no reason given reads as a bug.

// Sodium has no ICMR upper limit of its own, so the API sends `tul: null`.
const SODIUM = { name: 'Sodium', unit: 'mg', ear: null, tul: null, kind: 'ceiling' } as const

test('says what lowered a ceiling, and after which day', () => {
  render(
    <NutrientBar {...SODIUM} consumed={900} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.getByText('Lowered by 600 mg after Sunday')).toBeInTheDocument()
})

// A negative carry is not a carry to make up, and a sign in front of a number
// is easy to miss.
test('does not present a lowered ceiling as something carried', () => {
  render(
    <NutrientBar {...SODIUM} consumed={900} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.queryByText(/carried from/i)).not.toBeInTheDocument()
})

// The day is judged against the lowered ceiling, which is its limit: 1,500 mg is
// under Sunday's 2,000 mg but past today's 1,400 mg.
test('judges the day against the lowered ceiling', () => {
  render(
    <NutrientBar {...SODIUM} consumed={1500} target={1400} carriedIn={-600} carriedFrom="Sunday" />,
  )

  expect(screen.getByText('past the upper limit')).toBeInTheDocument()
})

// Monday morning after a salty Sunday, nothing has been logged yet -- coverage
// is 0 before the first bite. The lowered ceiling is set before then, so the
// reason for it must not wait for something to be measured.
test('explains a lowered ceiling before anything today is measured', () => {
  render(
    <NutrientBar
      {...SODIUM}
      consumed={0}
      target={1400}
      coverage={0}
      carriedIn={-600}
      carriedFrom="Sunday"
    />,
  )

  expect(screen.getByText('Lowered by 600 mg after Sunday')).toBeInTheDocument()
})
