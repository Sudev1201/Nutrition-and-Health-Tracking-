import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { weekStartIso } from '../plan/usePlan'
import type { WeeklyReport } from './types'

export function useWeeklyReport(start: string) {
  return useQuery({
    queryKey: ['reports', 'week', start],
    queryFn: () => api.get<WeeklyReport>(`/reports/week?start=${start}`),
    retry: false,
  })
}

/** An ISO calendar date from a Date's local parts, never its UTC ones. */
function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/**
 * The calendar date `days` after an ISO date, negative for before.
 *
 * Built from its parts, like `formatDay`, because `new Date('2026-08-16')` is UTC
 * midnight, which is still the 15th anywhere west of Greenwich.
 */
export function addDays(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return isoDate(new Date(year, month - 1, day + days))
}

/**
 * The Sunday before this week's Sunday. Its Saturday has ended, so it is the
 * latest week with a complete report. The week in progress would open on days
 * that count for nothing yet.
 */
export function lastCompleteWeekStart(from: Date = new Date()): string {
  return addDays(weekStartIso(from), -7)
}
