import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { expect, test, vi } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { FoodListField } from './FoodListField'
import type { FoodRef } from './FoodListField'

/** More than the six the list used to truncate to. */
function manyResults(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: `i${index}`,
    kind: 'ingredient',
    name: `Rice variety ${index}`,
    source: 'IFCT',
    is_editable: false,
  }))
}

function renderField(items: FoodRef[] = [], onChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <FoodListField
        label="Foods you particularly like"
        hint="Add as many as you want."
        searchLabel="Search foods you like"
        items={items}
        onChange={onChange}
      />
    </QueryClientProvider>,
  )
  return onChange
}

function search(term: string) {
  fireEvent.change(screen.getByRole('searchbox', { name: /search foods/i }), {
    target: { value: term },
  })
}

/*
 * Preferences must come from the food database so each one carries an id the
 * planner can act on. Truncating the matches to a handful hid most of what we
 * have -- "chicken" alone matches 44 rows across dishes and ingredients.
 */
test('offers every match, not just the first few', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(manyResults(25))))
  renderField()

  search('rice')

  expect(await screen.findByRole('button', { name: /add rice variety 0/i })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /add rice variety 24/i })).toBeInTheDocument()
})

test('asks the server for more than a page of matches', async () => {
  let requested: string | null = null
  server.use(
    http.get(apiUrl('/foods/search'), ({ request }) => {
      requested = new URL(request.url).searchParams.get('limit')
      return HttpResponse.json(manyResults(3))
    }),
  )
  renderField()

  search('rice')
  await screen.findByRole('button', { name: /add rice variety 0/i })

  expect(Number(requested)).toBeGreaterThan(20)
})

test('adding a food keeps the reference to the database row', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(manyResults(2))))
  const onChange = renderField()

  search('rice')
  await userEvent.click(await screen.findByRole('button', { name: /add rice variety 1/i }))

  expect(onChange).toHaveBeenCalledWith([
    { label: 'Rice variety 1', food_id: 'i1', food_kind: 'ingredient' },
  ])
})

/*
 * The list is the database's, not the user's typing. A free-text entry carries no
 * id, so the planner could only string-match it -- and it can never be costed.
 */
test('a food that is not in the database cannot be added', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json([])))
  renderField()

  search('unicorn steak')

  expect(await screen.findByText(/nothing in the food database matches/i)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /anyway/i })).not.toBeInTheDocument()
})

test('says when the match list was capped, so it does not look complete', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(manyResults(100))))
  renderField()

  search('a')

  expect(await screen.findByText(/first 100 matches/i)).toBeInTheDocument()
})

test('does not claim a cap when everything fitted', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(manyResults(12))))
  renderField()

  search('rice')

  await screen.findByRole('button', { name: /add rice variety 0/i })
  expect(screen.queryByText(/first 100 matches/i)).not.toBeInTheDocument()
})

test('the same food cannot be added twice', async () => {
  server.use(http.get(apiUrl('/foods/search'), () => HttpResponse.json(manyResults(2))))
  const existing = [{ label: 'Rice variety 1', food_id: 'i1', food_kind: 'ingredient' as const }]
  const onChange = renderField(existing)

  search('rice')
  await userEvent.click(await screen.findByRole('button', { name: /add rice variety 1/i }))

  expect(onChange).not.toHaveBeenCalled()
})

test('an added food can be removed again', async () => {
  const existing = [{ label: 'Curd', food_id: 'i9', food_kind: 'ingredient' as const }]
  const onChange = renderField(existing)

  await userEvent.click(screen.getByRole('button', { name: /remove curd/i }))

  expect(onChange).toHaveBeenCalledWith([])
})
