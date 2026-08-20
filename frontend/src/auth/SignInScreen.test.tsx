import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { SignInScreen } from './SignInScreen'

const GSI_SRC = 'https://accounts.google.com/gsi/client'

const initialize = vi.fn()
const renderButton = vi.fn()

beforeEach(() => {
  initialize.mockClear()
  renderButton.mockClear()

  // Stand in for the script having already loaded: jsdom never fetches it, so
  // the component's "script is already present" path is what these exercise.
  vi.stubGlobal('google', { accounts: { id: { initialize, renderButton } } })
  const script = document.createElement('script')
  script.src = GSI_SRC
  document.body.appendChild(script)
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelectorAll(`script[src="${GSI_SRC}"]`).forEach((node) => node.remove())
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <SignInScreen />
    </QueryClientProvider>,
  )
}

test('sets up the Google button when the identity script is available', () => {
  renderScreen()

  expect(initialize).toHaveBeenCalledOnce()
  expect(renderButton).toHaveBeenCalledOnce()
})

/*
 * Regression: the effect depended on the whole `useMutation` object, which is a
 * new identity on every render. Every re-render therefore re-ran it — appending
 * another GSI script and calling initialize again, which Google warns about in
 * the console ("called multiple times ... only the last initialized instance
 * will be used").
 */
test('does not re-initialize Google Identity on a re-render', () => {
  const { rerender } = renderScreen()

  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <SignInScreen />
    </QueryClientProvider>,
  )

  expect(initialize).toHaveBeenCalledOnce()
})

// The old cleanup removed the script on unmount, so a remount re-added it.
test('reuses the Google script rather than adding another', () => {
  const { unmount } = renderScreen()
  unmount()
  renderScreen()

  expect(document.querySelectorAll(`script[src="${GSI_SRC}"]`)).toHaveLength(1)
})

/*
 * `google.accounts.id` is a page-level singleton. React StrictMode invokes
 * effects twice on mount in development, which is what was producing the
 * "initialize() is called multiple times" warning in the real browser.
 */
test('initializes Google Identity only once across remounts', () => {
  const { unmount } = renderScreen()
  unmount()
  renderScreen()

  expect(initialize).toHaveBeenCalledOnce()
})

// The button container is a fresh element on each mount, so it does need
// re-rendering even though initialize must not run again.
test('renders the button again on a remount', () => {
  const { unmount } = renderScreen()
  unmount()
  renderScreen()

  expect(renderButton).toHaveBeenCalledTimes(2)
})
