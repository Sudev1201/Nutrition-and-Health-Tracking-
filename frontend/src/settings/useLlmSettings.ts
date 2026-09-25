import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { LlmKeyIn, LlmSettings } from './types'

/** The Plan screen reads it too: it offers descriptions only with a key Anthropic accepted. */
export const LLM_SETTINGS_KEY = ['settings', 'llm'] as const

export function useLlmSettings() {
  return useQuery({
    queryKey: LLM_SETTINGS_KEY,
    queryFn: () => api.get<LlmSettings>('/settings/llm'),
    retry: false,
  })
}

export function useSaveLlmKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LlmKeyIn) => api.put<LlmSettings>('/settings/llm', body),
    // A mutation remembers what it was called with, and here that is the key.
    // The screen resets the mutation once it settles, and with no cache time
    // the mutation cache lets go of it straight after, rather than five minutes on.
    gcTime: 0,
    // The answer is the whole screen's state, so there is nothing to refetch.
    onSuccess: (settings) => queryClient.setQueryData(LLM_SETTINGS_KEY, settings),
  })
}

export function useDeleteLlmKey() {
  const queryClient = useQueryClient()
  return useMutation({
    // 204, with nothing to show, so the settings are read again.
    mutationFn: () => api.del<null>('/settings/llm'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }),
  })
}
