import { useCallback, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { api } from '../lib/api'
import { formatAmount } from '../lib/format'
import { SLOT_LABELS, SLOT_ORDER } from '../log/types'
import type { MealSlot } from '../log/types'
import { FULL_MATCH_LIMIT, useFoodSearch } from '../foods/useFoodSearch'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { NumberInput, Select } from '../ui/fields'
import { SearchField } from '../ui/SearchField'
import type { UsualIntakeAnswer } from './types'

/** A sensible default weight so a food can be added in one tap. */
const DEFAULT_GRAMS = 150

interface CostResponse {
  totals: Record<string, number>
}

/**
 * Total a list of foods server-side.
 *
 * The wizard needs a running figure before there is a profile to attach the list
 * to, and the per-100g values live in the database — so the sum is computed by
 * the backend from the items alone rather than guessed in the browser.
 */
function useCostOfDay() {
  return useMutation({
    mutationFn: (items: UsualIntakeAnswer[]) =>
      api.post<CostResponse>('/foods/nutrients', {
        items: items.map((item) => ({
          food_id: item.food_id,
          food_kind: item.food_kind,
          grams: item.grams,
        })),
      }),
  })
}

export function UsualIntakeStep({
  answers,
  update,
}: {
  answers: { usual_intake: UsualIntakeAnswer[] }
  update: (changes: { usual_intake: UsualIntakeAnswer[] }) => void
}) {
  const [slot, setSlot] = useState<MealSlot>('breakfast')
  const [term, setTerm] = useState('')
  const [grams, setGrams] = useState(String(DEFAULT_GRAMS))
  const { data: results, isFetching } = useFoodSearch(term, FULL_MATCH_LIMIT)
  const handleSearch = useCallback((value: string) => setTerm(value), [])
  const cost = useCostOfDay()

  const items = answers.usual_intake

  function add(foodId: string, foodKind: 'dish' | 'ingredient', label: string) {
    const parsed = Number.parseFloat(grams)
    const next = [
      ...items,
      {
        slot,
        label,
        food_id: foodId,
        food_kind: foodKind,
        grams: Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_GRAMS,
      },
    ]
    update({ usual_intake: next })
    setTerm('')
    cost.mutate(next)
  }

  function remove(index: number) {
    const next = items.filter((_, position) => position !== index)
    update({ usual_intake: next })
    if (next.length > 0) cost.mutate(next)
    else cost.reset()
  }

  const energy = cost.data?.totals.energy

  return (
    <>
      {/*
        Onboarding never asks for a calorie figure -- most people do not know
        theirs, and a guess would be worse than nothing. Describing a usual day as
        real foods is what makes the baseline computable at all.
      */}
      <p className="mb-3 text-sm text-text-muted">
        Add the things you normally eat on an ordinary day. This isn’t your target — it’s so the
        app knows where you are starting from, and the first week is a step rather than a jump.
        You can skip this and come back to it.
      </p>

      <div className="mb-3 flex gap-2">
        <div className="flex-1">
          <label className="mb-1 block text-sm font-medium" htmlFor="usual-slot">
            Meal
          </label>
          <Select
            id="usual-slot"
            value={slot}
            onChange={(event) => setSlot(event.target.value as MealSlot)}
          >
            {SLOT_ORDER.map((value) => (
              <option key={value} value={value}>
                {SLOT_LABELS[value]}
              </option>
            ))}
          </Select>
        </div>
        <div className="w-28">
          <label className="mb-1 block text-sm font-medium" htmlFor="usual-grams">
            Grams
          </label>
          <NumberInput
            id="usual-grams"
            value={grams}
            onChange={(event) => setGrams(event.target.value)}
          />
        </div>
      </div>

      <SearchField
        label="Search foods to add to your usual day"
        placeholder="idli, rice, sambar…"
        onSearch={handleSearch}
      />

      {term !== '' && (
        <div className="mt-2 overflow-hidden rounded-card border border-border">
          {isFetching && <p className="p-3 text-sm text-text-muted">Searching…</p>}

          {!isFetching && results !== undefined && results.length > 0 && (
            <ul className="max-h-72 divide-y divide-border overflow-y-auto">
              {results.map((result) => (
                <li key={`${result.kind}-${result.id}`}>
                  <button
                    type="button"
                    aria-label={`Add ${result.name}`}
                    onClick={() => add(result.id, result.kind, result.name)}
                    className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm hover:bg-surface-alt"
                  >
                    <Plus className="size-4 shrink-0 text-accent" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{result.name}</span>
                    <Badge>{result.source}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/*
            No free-text fallback here, unlike the likes and avoid lists: an item
            with no food behind it cannot be costed, and silently contributing
            zero calories would understate the baseline.
          */}
          {!isFetching && results !== undefined && results.length === 0 && (
            <p className="p-3 text-sm text-text-muted">
              Nothing matches “{term}”. Only foods in the database can be counted, so try a
              simpler name — the individual ingredients usually work.
            </p>
          )}

          {!isFetching && results !== undefined && results.length >= FULL_MATCH_LIMIT && (
            <p className="border-t border-border p-2 text-xs text-text-muted">
              Showing the first {FULL_MATCH_LIMIT} matches — type more to narrow it down.
            </p>
          )}
        </div>
      )}

      {items.length > 0 && (
        <Card className="mt-4 p-0">
          <ul className="divide-y divide-border">
            {items.map((item, index) => (
              <li key={`${item.food_id}-${index}`} className="flex items-center gap-2 px-3 py-2">
                <span className="w-24 shrink-0 text-xs text-text-muted">
                  {SLOT_LABELS[item.slot]}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">{item.label}</span>
                <span className="shrink-0 text-xs text-text-muted">{item.grams} g</span>
                <Button
                  variant="quiet"
                  aria-label={`Remove ${item.label}`}
                  className="min-h-9 px-1"
                  onClick={() => remove(index)}
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>

          <div className="border-t border-border px-3 py-2 text-sm">
            {cost.isPending && <span className="text-text-muted">Working it out…</span>}
            {cost.isError && (
              <span role="alert" className="text-above-limit">
                That could not be totalled just now.
              </span>
            )}
            {energy !== undefined && !cost.isPending && (
              <span>
                A usual day for you is about{' '}
                <strong className="font-semibold">{formatAmount(energy, 'kcal')} kcal</strong>.
                Your computed target appears on Today once you finish.
              </span>
            )}
          </div>
        </Card>
      )}
    </>
  )
}
