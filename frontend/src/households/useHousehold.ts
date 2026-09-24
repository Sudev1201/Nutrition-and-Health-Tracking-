import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'

export interface Member {
  user_id: string
  name: string
  email: string
  share_progress: boolean
  share_health: boolean
}

export interface Household {
  id: string
  name: string
  members: Member[]
}

/**
 * One member's week, as the household may see it: counts of days, never a
 * nutrient or a target. CONTRACT for `GET /households/progress?start=`,
 * implemented by the backend's `app/households/router.py`.
 */
export interface MemberProgress {
  user_id: string
  name: string
  is_me: boolean
  /** Whether you may see this member's counts. Always true on your own row. */
  shared: boolean
  /** Logged days that have ended. Null when not shared, or with no profile yet. */
  tracked_days: number | null
  /** Nutrient-days on track: one nutrient on one logged day, met as the report meets it. */
  nutrient_days_met: number | null
  nutrient_days_measured: number | null
}

export interface HouseholdProgress {
  /** The Sunday the week starts on. */
  start_date: string
  /** You first, then everyone else in the order they joined. */
  members: MemberProgress[]
}

export function useHousehold() {
  return useQuery({
    queryKey: ['household'],
    queryFn: async () => {
      try {
        return await api.get<Household>('/households/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    retry: false,
  })
}

/**
 * One week's progress for the whole household. Null when you are not in one (a
 * 404), or when the week has not begun where your account keeps time (a 422:
 * this browser's calendar can reach a Sunday first). Neither is an error.
 */
export function useHouseholdProgress(start: string) {
  return useQuery({
    // Under 'household', so every invalidation of the household -- a change of
    // what you share, above all -- refreshes the counts with it.
    queryKey: ['household', 'progress', start],
    queryFn: async () => {
      try {
        return await api.get<HouseholdProgress>(`/households/progress?start=${start}`)
      } catch (error) {
        // 404: you are no longer in a household. 422: this browser's Sunday came
        // before the account's, so the week has not begun where the account keeps
        // time. Both are calm states, and the card shows nothing.
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
          return null
        }
        throw error
      }
    },
    retry: false,
  })
}

export function useCreateHousehold() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.post<Household>('/households', { name }),
    onSuccess: (household) => queryClient.setQueryData(['household'], household),
  })
}

export function useInvite() {
  return useMutation({
    mutationFn: (email: string) =>
      api.post<{ token: string; email: string }>('/households/invites', { email }),
  })
}

export function useAcceptInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) =>
      api.post<Household>('/households/invites/accept', { token }),
    onSuccess: (household) => queryClient.setQueryData(['household'], household),
  })
}

export function useLeaveHousehold() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/households/leave', {}),
    onSuccess: () => {
      queryClient.setQueryData(['household'], null)
      // The old household's weeks are not yours to see any more, and a household
      // started or joined next must not open on them while its own counts load.
      queryClient.removeQueries({ queryKey: ['household', 'progress'] })
    },
  })
}

export function useUpdateVisibility() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: { share_progress?: boolean; share_health?: boolean }) =>
      api.patch('/households/visibility', changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['household'] }),
  })
}
