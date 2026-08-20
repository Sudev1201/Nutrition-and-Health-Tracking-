import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, test } from 'vitest'
import { BottomTabs } from './BottomTabs'
import { Sidebar } from './Sidebar'

function renderAt(ui: React.ReactElement, path: string) {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>)
}

test('the phone tab bar offers the five primary destinations', () => {
  renderAt(<BottomTabs />, '/')

  for (const label of ['Today', 'Log', 'Plan', 'Report', 'More']) {
    expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
  }
})

test('the tab bar marks the destination you are on', () => {
  renderAt(<BottomTabs />, '/plan')

  expect(screen.getByRole('link', { name: 'Plan' })).toHaveAttribute('aria-current', 'page')
})

// "/" is a prefix of every other route, so without an exact match Today lights up
// on every screen in the app and the tab bar stops telling you where you are.
test('Today is not marked current while you are somewhere else', () => {
  renderAt(<BottomTabs />, '/plan')

  expect(screen.getByRole('link', { name: 'Today' })).not.toHaveAttribute('aria-current')
})

// On a wide screen there is room for everything, so burying five destinations
// behind a "More" tab would be a phone constraint imported for no reason.
test('the sidebar lists the More destinations inline rather than behind a tab', () => {
  renderAt(<Sidebar />, '/')

  for (const label of ['Weight', 'Cycle', 'Household', 'Reminders', 'Profile']) {
    expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
  }
  expect(screen.queryByRole('link', { name: 'More' })).not.toBeInTheDocument()
})

test('the sidebar marks the destination you are on', () => {
  renderAt(<Sidebar />, '/report')

  expect(screen.getByRole('link', { name: 'Report' })).toHaveAttribute('aria-current', 'page')
})
