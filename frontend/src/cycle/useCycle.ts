import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { CycleDayInput, CycleState, ScreeningAnswers } from './types'

/** `date` is the user's today: coaching such as "days 1–3" is read against it. */
export function useCycle(date: string) {
  return useQuery({
    queryKey: ['cycle', date],
    queryFn: () => api.get<CycleState>(`/cycle?date=${date}`),
    retry: false,
  })
}

function useCycleMutation<TVariables>(mutationFn: (variables: TVariables) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    // Settled rather than succeeded: a request that failed after the server acted
    // (an erase that timed out, say) must still show what the server now holds.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['cycle'] }),
  })
}

export function useSetCycleEnabled() {
  return useCycleMutation((enabled: boolean) => api.patch('/cycle', { enabled }))
}

export function useSaveCycleDay() {
  return useCycleMutation(({ date, day }: { date: string; day: CycleDayInput }) =>
    api.put(`/cycle/days/${date}`, day),
  )
}

export function useClearCycleDay() {
  return useCycleMutation((date: string) => api.del(`/cycle/days/${date}`))
}

/** Sent without a date, so the server dates the answers with the user's own today. */
export function useSaveScreening() {
  return useCycleMutation((answers: ScreeningAnswers) => api.post('/cycle/screening', answers))
}

export function useEraseCycle() {
  return useCycleMutation<void>(() => api.del('/cycle'))
}
