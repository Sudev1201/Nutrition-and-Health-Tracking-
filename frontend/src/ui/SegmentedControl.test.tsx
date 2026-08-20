import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { SegmentedControl } from './SegmentedControl'

const OPTIONS = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
]

test('offers every option', () => {
  render(<SegmentedControl label="View" options={OPTIONS} value="day" onChange={() => {}} />)

  expect(screen.getByRole('radio', { name: 'Day' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'Week' })).toBeInTheDocument()
})

test('marks the selected option for assistive technology', () => {
  render(<SegmentedControl label="View" options={OPTIONS} value="week" onChange={() => {}} />)

  expect(screen.getByRole('radio', { name: 'Week' })).toBeChecked()
  expect(screen.getByRole('radio', { name: 'Day' })).not.toBeChecked()
})

test('reports the option that was chosen', async () => {
  const onChange = vi.fn()
  render(<SegmentedControl label="View" options={OPTIONS} value="day" onChange={onChange} />)

  await userEvent.click(screen.getByRole('radio', { name: 'Week' }))

  expect(onChange).toHaveBeenCalledWith('week')
})
