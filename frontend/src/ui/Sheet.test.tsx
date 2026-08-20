import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import { Sheet } from './Sheet'

test('shows its content while open', () => {
  render(
    <Sheet open title="Log dinner" onClose={() => {}}>
      <p>What did you eat?</p>
    </Sheet>,
  )

  expect(screen.getByText('What did you eat?')).toBeInTheDocument()
})

test('renders nothing while closed', () => {
  render(
    <Sheet open={false} title="Log dinner" onClose={() => {}}>
      <p>What did you eat?</p>
    </Sheet>,
  )

  expect(screen.queryByText('What did you eat?')).not.toBeInTheDocument()
})

test('is a dialog named by its title', () => {
  render(
    <Sheet open title="Log dinner" onClose={() => {}}>
      <p>What did you eat?</p>
    </Sheet>,
  )

  expect(screen.getByRole('dialog', { name: 'Log dinner' })).toBeInTheDocument()
})

test('closes when the close control is used', async () => {
  const onClose = vi.fn()
  render(
    <Sheet open title="Log dinner" onClose={onClose}>
      <p>What did you eat?</p>
    </Sheet>,
  )

  await userEvent.click(screen.getByRole('button', { name: /close/i }))

  expect(onClose).toHaveBeenCalledOnce()
})
