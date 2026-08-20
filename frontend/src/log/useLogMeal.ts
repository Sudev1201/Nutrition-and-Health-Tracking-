import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { NewDiaryEntry } from './types'

export function useLogMeal() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (entry: NewDiaryEntry) => api.post('/diary/entries', entry),
    onSuccess: () => {
      // Both the diary and the day's totals change when a meal is logged, and
      // the compensation ledger means tomorrow's targets can move too.
      queryClient.invalidateQueries({ queryKey: ['diary'] })
      queryClient.invalidateQueries({ queryKey: ['targets'] })
    },
  })
}

/**
 * Turn what the form holds into the request body.
 *
 * A portion is sent as the household measure the user chose; the absolute goes
 * with it so the server does not have to re-derive it. When the portion was
 * weighed instead, the measure is null and the weight stands alone.
 */
export function buildDiaryEntry({
  date,
  slot,
  foodId,
  foodKind,
  portion,
  isEstimated,
}: {
  date: string
  slot: NewDiaryEntry['slot']
  foodId: string
  foodKind: NewDiaryEntry['food_kind']
  portion: { measure_name: string | null; quantity: number | null; grams: number | null }
  isEstimated: boolean
}): NewDiaryEntry {
  return {
    date,
    slot,
    food_id: foodId,
    food_kind: foodKind,
    measure_name: portion.measure_name,
    quantity: portion.quantity,
    // Sent only when the portion was weighed; otherwise the measure defines it
    // and the server resolves the weight from its own figures.
    grams: portion.measure_name === null ? portion.grams : null,
    is_estimated: isEstimated,
  }
}
