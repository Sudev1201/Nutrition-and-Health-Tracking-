import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { FoodSearchScreen } from './FoodSearchScreen'

const RESULTS = [
  { id: 'd1', kind: 'dish', name: 'Ven Pongal', source: 'authored', is_editable: true },
  { id: 'i1', kind: 'ingredient', name: 'Rice, raw, milled', source: 'IFCT', is_editable: false },
]

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <FoodSearchScreen />
    </QueryClientProvider>,
  )
}

function search(term: string) {
  fireEvent.change(screen.getByRole('searchbox', { name: /search/i }), {
    target: { value: term },
  })
}

test('lists what the food database returns', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(RESULTS)))
  renderScreen()

  search('pongal')

  expect(await screen.findByText('Ven Pongal')).toBeInTheDocument()
  expect(await screen.findByText('Rice, raw, milled')).toBeInTheDocument()
})

// Dishes and ingredients are both reachable from this one endpoint and behave
// differently when logged, so the list has to say which is which.
test('tells dishes apart from ingredients', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(RESULTS)))
  renderScreen()

  search('pongal')

  expect(await screen.findByText('Dish')).toBeInTheDocument()
  expect(await screen.findByText('Ingredient')).toBeInTheDocument()
})

// Every row in the database is source-tagged because IFCT, USDA and INDB use
// different conventions. Showing the provenance is the spec's own commitment.
test('shows where each food’s data came from', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(RESULTS)))
  renderScreen()

  search('pongal')

  expect(await screen.findByText('IFCT')).toBeInTheDocument()
})

test('sends the typed term to the server', async () => {
  let received: string | null = null
  server.use(
    http.get(apiUrl('/foods/search'), ({ request }) => {
      received = new URL(request.url).searchParams.get('q')
      return HttpResponse.json(RESULTS)
    }),
  )
  renderScreen()

  search('pongal')
  await screen.findByText('Ven Pongal')

  expect(received).toBe('pongal')
})

test('says so when nothing matches', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json([])))
  renderScreen()

  search('zzzz')

  expect(await screen.findByText(/nothing matched/i)).toBeInTheDocument()
})

// A failed search must not render as "no results" -- that would tell the user
// their food is missing from the database when the request simply broke.
test('reports a failed search rather than showing it as no results', async () => {
  server.use(
    http.get(apiUrl('/foods/search'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  search('pongal')

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not be searched/i)
})
