import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { Diary } from '../log/types'
import type { TodayTargets } from './types'

/** Local calendar date — the day boundary is the user's, not UTC's. */
export function todayIso(): string {
  const now = new Date()
  const offsetMs = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10)
}

export function useTodayTargets(date: string) {
  return useQuery({
    queryKey: ['targets', 'today', date],
    queryFn: () => api.get<TodayTargets>(`/targets/today?date=${date}`),
    retry: false,
  })
}

export function useDiary(date: string) {
  return useQuery({
    queryKey: ['diary', date],
    queryFn: () => api.get<Diary>(`/diary?date=${date}`),
    retry: false,
  })
}
