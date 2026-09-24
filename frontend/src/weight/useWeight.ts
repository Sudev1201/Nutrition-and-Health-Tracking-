import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { NewWeighIn, WeightTrend } from './types'

export function useWeight() {
  return useQuery({
    queryKey: ['weight'],
    queryFn: () => api.get<WeightTrend>('/weight'),
    retry: false,
  })
}

/*
 * A weigh-in reaches further than this screen. It is the profile's weight, so
 * the profile summary and the baseline move, and it can recalibrate today's
 * targets. It never rewrites a stored plan, so the plan is left alone.
 */
function afterWeighIn(queryClient: QueryClient) {
  for (const queryKey of [['weight'], ['targets'], ['profile']]) {
    queryClient.invalidateQueries({ queryKey })
  }
}

export function useAddWeighIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (weighIn: NewWeighIn) => api.post<WeightTrend>('/weight', weighIn),
    onSuccess: () => afterWeighIn(queryClient),
  })
}

export function useRemoveWeighIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (date: string) => api.del(`/weight/${date}`),
    onSuccess: () => afterWeighIn(queryClient),
  })
}
