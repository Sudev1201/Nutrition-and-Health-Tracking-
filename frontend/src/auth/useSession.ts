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

/*
 * Everything but the session is one account's data. The cache outlives a sign-out
 * -- RequireAuth swaps in the sign-in screen at the same route, with no reload --
 * so on a shared device the next account would otherwise be shown the previous
 * one's cycle days and weigh-ins until its own requests land.
 */
const notSession = {
  predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[0] !== 'session',
}

export function useSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (credential: string) =>
      api.post<SessionUser>('/auth/google', { credential }),
    onSuccess: (user) => {
      // Also covers a session that expired rather than signed out.
      queryClient.removeQueries(notSession)
      queryClient.setQueryData(['session'], user)
    },
  })
}

export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout', {}),
    onSuccess: () => {
      // The session first, so RequireAuth unmounts the screens; clearing the cache
      // before this leaves them subscribed to removed queries, and sign-out stalls.
      queryClient.setQueryData(['session'], null)
      queryClient.removeQueries(notSession)
    },
  })
}
