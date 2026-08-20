import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { MealSlot } from '../log/types'

interface SkipRequest {
  date: string
  slot: MealSlot
}

/**
 * Mark a slot as deliberately not eaten, or undo that.
 *
 * Any of the five slots can be skipped, not only the optional snacks — no time
 * to eat and a fast are both ordinary reasons to miss a main meal, and recording
 * those as `empty` throws away the fact that the user told us.
 *
 * Both the diary and the targets are invalidated: the slot's state changes, and
 * a day the user has now said something about is no longer a day they simply
 * did not open the app on.
 */
export function useSkipSlot() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ date, slot, skipped }: SkipRequest & { skipped: boolean }) =>
      skipped
        ? api.post<unknown>('/diary/skips', { date, slot })
        : api.del<unknown>('/diary/skips', { date, slot }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['diary'] })
      void queryClient.invalidateQueries({ queryKey: ['targets'] })
    },
  })
}
