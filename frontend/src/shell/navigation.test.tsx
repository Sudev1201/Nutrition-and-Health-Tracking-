import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, test } from 'vitest'
import { BottomTabs } from './BottomTabs'
import { MoreScreen } from './MoreScreen'
import { Sidebar } from './Sidebar'

/** Behind the More tab on a phone, inline in the sidebar, in this order. */
const MORE_LABELS = ['Weight', 'Cycle', 'Household', 'Reminders', 'AI descriptions', 'Profile']

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

// On a wide screen there is room for everything, so burying six destinations
// behind a "More" tab would be a phone constraint imported for no reason.
test('the sidebar lists the More destinations inline rather than behind a tab', () => {
  renderAt(<Sidebar />, '/')

  for (const label of MORE_LABELS) {
    expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
  }
  expect(screen.queryByRole('link', { name: 'More' })).not.toBeInTheDocument()
})

test('the sidebar marks the destination you are on', () => {
  renderAt(<Sidebar />, '/report')

  expect(screen.getByRole('link', { name: 'Report' })).toHaveAttribute('aria-current', 'page')
})

test('the phone’s More screen lists the same destinations, in the same order', () => {
  renderAt(<MoreScreen />, '/more')

  expect(screen.getAllByRole('link').map((link) => link.textContent)).toStrictEqual(MORE_LABELS)
  expect(screen.getByRole('link', { name: 'AI descriptions' })).toHaveAttribute(
    'href',
    '/ai-descriptions',
  )
})
