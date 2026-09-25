import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, postWithHeaders } from '../lib/api'
import { LLM_SETTINGS_KEY } from '../settings/useLlmSettings'
import type { CookingView, WeekPlan } from './types'

/** The plan week runs Sunday to Saturday, per the spec. */
export function weekStartIso(from: Date = new Date()): string {
  const start = new Date(from)
  start.setDate(start.getDate() - start.getDay())
  const offsetMs = start.getTimezoneOffset() * 60_000
  return new Date(start.getTime() - offsetMs).toISOString().slice(0, 10)
}

export function useWeekPlan(start: string) {
  return useQuery({
    queryKey: ['plan', 'week', start],
    queryFn: () => api.get<WeekPlan>(`/plan/week?start=${start}`),
    retry: false,
  })
}

export function useCookingView(date: string, enabled = true) {
  return useQuery({
    queryKey: ['plan', 'cooking', date],
    queryFn: () => api.get<CookingView>(`/plan/cooking?date=${date}`),
    retry: false,
    enabled,
  })
}

export function useToggleLock() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, locked }: { itemId: string; locked: boolean }) =>
      api.patch(`/plan/items/${itemId}`, { locked }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })
}

export function useSwapItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (itemId: string) => api.post(`/plan/items/${itemId}/swap`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })
}

export function useRegenerateWeek() {
  const queryClient = useQueryClient()
  return useMutation({
    // The Plan screen reads this key from the mutation cache, so its lockout
    // holds across leaving the screen and coming back.
    mutationKey: ['plan', 'regenerate'],
    mutationFn: (start: string) => api.post('/plan/week/regenerate', { start }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })
}

/** What a polish answers: the whole week, and how many dishes got text this time. */
export interface PolishResult {
  week: WeekPlan
  /**
   * The `X-Dishes-Described` header. 0 when Claude added nothing: a refusal, an
   * answer cut short and text the server's check turned down all answer 200 with
   * the week as it was. Null when the header is missing or is not a whole
   * number, for example when CORS does not expose it. That counts as unknown,
   * and the screen says nothing.
   */
  described: number | null
}

/**
 * Ask Claude for descriptions of this week's dishes, with the user's own key
 * (plan 9). The server sends only the dishes with no current text, so asking
 * again costs nothing for the ones already described.
 */
export function usePolishWeek() {
  const queryClient = useQueryClient()
  return useMutation({
    // Read by the Plan screen from the mutation cache, like ['plan', 'regenerate'].
    mutationKey: ['plan', 'polish'],
    mutationFn: async (start: string): Promise<PolishResult> => {
      const { data, headers } = await postWithHeaders<WeekPlan>('/plan/week/polish', { start })
      const count = headers.get('X-Dishes-Described')
      const described = count !== null && /^\d+$/.test(count) ? Number(count) : null
      return { week: data, described }
    },
    // The answer is the whole week, descriptions attached, so there is nothing to
    // refetch.
    onSuccess: ({ week }, start) => queryClient.setQueryData(['plan', 'week', start], week),
    // A key Anthropic refused is marked on the server, and the button goes with it.
    onError: () => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }),
  })
}
