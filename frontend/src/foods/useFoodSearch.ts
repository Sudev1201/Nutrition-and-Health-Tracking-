import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface FoodResult {
  id: string
  kind: 'dish' | 'ingredient'
  name: string
  /** IFCT | USDA | INDB | authored | user — every row is source-tagged. */
  source: string
  is_editable: boolean
}

/**
 * Enough to cover any realistic term in one go: "chicken", the broadest sensible
 * search, matches 44 rows across dishes and ingredients. A single letter matches
 * over 1,500, which is why there is still a ceiling.
 */
export const FULL_MATCH_LIMIT = 100

export function useFoodSearch(term: string, limit = 20) {
  return useQuery({
    queryKey: ['foods', 'search', term, limit],
    queryFn: () =>
      api.get<FoodResult[]>(`/foods/search?q=${encodeURIComponent(term)}&limit=${limit}`),
    // The endpoint answers a blank query with a 422 by design, so no request is
    // made until there is something to search for.
    enabled: term !== '',
    retry: false,
  })
}
