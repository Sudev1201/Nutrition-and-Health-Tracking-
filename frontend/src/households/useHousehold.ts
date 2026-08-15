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

export function useUpdateVisibility() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: { share_progress?: boolean; share_health?: boolean }) =>
      api.patch('/households/visibility', changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['household'] }),
  })
}
