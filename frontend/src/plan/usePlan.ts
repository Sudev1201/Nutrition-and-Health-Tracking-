import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
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

export function useCookingView(date: string) {
  return useQuery({
    queryKey: ['plan', 'cooking', date],
    queryFn: () => api.get<CookingView>(`/plan/cooking?date=${date}`),
    retry: false,
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
    mutationFn: (start: string) => api.post('/plan/week/regenerate', { start }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })
}
