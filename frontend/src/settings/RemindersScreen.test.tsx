import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { RemindersScreen } from './RemindersScreen'

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <RemindersScreen />
    </QueryClientProvider>,
  )
}

test('lists every meal slot with its usual time', async () => {
  renderScreen()

  expect(await screen.findByRole('switch', { name: /breakfast · 08:00/i })).toBeInTheDocument()
  expect(await screen.findByRole('switch', { name: /dinner · 20:30/i })).toBeInTheDocument()
})

// The optional mid-morning snack must not nag someone who rarely eats it.
test('shows the optional snack reminder as off', async () => {
  renderScreen()

  expect(
    await screen.findByRole('switch', { name: /mid-morning snack/i }),
  ).not.toBeChecked()
})

test('turning a slot’s reminder off sends just that slot', async () => {
  const patched = vi.fn()
  server.use(
    http.patch(apiUrl('/settings/reminders'), async ({ request }) => {
      patched(await request.json())
      return HttpResponse.json({})
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('switch', { name: /dinner/i }))

  expect(patched).toHaveBeenCalledWith({ slot: 'dinner', reminder_on: false })
})

// iOS only delivers web push to a PWA installed on the home screen, which is a
// real constraint the user has to be told about rather than left to discover.
test('explains the iPhone install requirement when notifications are off', async () => {
  renderScreen()

  expect(await screen.findByText(/add this app to your home screen/i)).toBeInTheDocument()
})
