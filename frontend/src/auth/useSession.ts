import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'

export interface SessionUser {
  id: string
  email: string
  name: string
  timezone: string
}

export function useSession() {
  const query = useQuery({
    queryKey: ['session'],
    queryFn: async () => {
      try {
        return await api.get<SessionUser>('/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    retry: false,
  })

  return { user: query.data ?? null, isLoading: query.isLoading }
}

export function useSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credential: string) =>
      api.post<SessionUser>('/auth/google', { credential }),
    onSuccess: (user) => queryClient.setQueryData(['session'], user),
  })
}

export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout', {}),
    onSuccess: () => queryClient.setQueryData(['session'], null),
  })
}
