import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { SearchField } from './SearchField'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function typeInto(term: string) {
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search foods' }), {
    target: { value: term },
  })
}

async function waitOutTheDebounce() {
  await act(async () => {
    vi.advanceTimersByTime(300)
  })
}

// The food database is searched server-side. Firing on every keystroke would send
// six requests for "pongal" and race their responses against each other.
test('does not search while the user is still typing', () => {
  const onSearch = vi.fn()
  render(<SearchField label="Search foods" onSearch={onSearch} />)

  typeInto('pongal')

  expect(onSearch).not.toHaveBeenCalled()
})

test('searches once the typing settles, with the final term', async () => {
  const onSearch = vi.fn()
  render(<SearchField label="Search foods" onSearch={onSearch} />)

  typeInto('pong')
  typeInto('pongal')
  await waitOutTheDebounce()

  expect(onSearch).toHaveBeenCalledExactlyOnceWith('pongal')
})

// GET /foods/search rejects a blank query with a 422 rather than returning twenty
// arbitrary rows, so the client must not send one.
test('never searches for a term that is only whitespace', async () => {
  const onSearch = vi.fn()
  render(<SearchField label="Search foods" onSearch={onSearch} />)

  typeInto('   ')
  await waitOutTheDebounce()

  expect(onSearch).not.toHaveBeenCalled()
})

// The term is trimmed before it reaches the server so " pongal " and "pongal"
// are one cache key, not two.
test('trims the term it searches for', async () => {
  const onSearch = vi.fn()
  render(<SearchField label="Search foods" onSearch={onSearch} />)

  typeInto('  pongal  ')
  await waitOutTheDebounce()

  expect(onSearch).toHaveBeenCalledExactlyOnceWith('pongal')
})
