import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatAmount } from '../lib/format'
import { Field, NumberInput, Select } from '../ui/fields'
import { QUANTITIES, quantityLabel } from './portion'
import type { Measure, Portion } from './portion'

function useMeasures(foodId: string | null, foodKind: string | null) {
  return useQuery({
    queryKey: ['foods', foodId, foodKind, 'measures'],
    queryFn: () => api.get<{ measures: Measure[] }>(`/foods/${foodKind}/${foodId}/measures`),
    enabled: foodId !== null && foodKind !== null,
    retry: false,
  })
}

/**
 * A portion, in the two units it needs to be in at once.
 *
 * The household measure is what the user recognises; the absolute is what the
 * nutrient tables are expressed in. They stay linked — choosing "½ bowl" fills
 * the absolute in — but the absolute can be overridden by anyone with scales,
 * which then stands on its own.
 */
export function PortionField({
  foodId,
  foodKind,
  value,
  onChange,
}: {
  foodId: string | null
  foodKind: 'dish' | 'ingredient' | null
  value: Portion
  onChange: (portion: Portion) => void
}) {
  const { data, isPending } = useMeasures(foodId, foodKind)
  // Memoised because the effect below depends on it: `data?.measures ?? []`
  // builds a fresh array on every render, which would re-run the effect forever.
  const measures = useMemo<Measure[]>(() => data?.measures ?? [], [data])
  const [weighed, setWeighed] = useState(false)
  const initialisedFor = useRef<string | null>(null)

  const selected = measures.find((measure) => measure.name === value.measure_name) ?? null

  /*
   * Open on the food's own measure, so the common case is one tap.
   *
   * Guarded to run once per food rather than whenever `measure_name` is null:
   * weighing a portion deliberately clears the measure, and without the guard
   * this effect fired straight back and overwrote the weight the user typed.
   */
  useEffect(() => {
    if (foodId === null || measures.length === 0) return
    if (initialisedFor.current === foodId) return

    initialisedFor.current = foodId
    const preferred = measures.find((measure) => measure.is_default) ?? measures[0]
    onChange({ measure_name: preferred.name, quantity: 1, grams: preferred.grams })
  }, [foodId, measures, onChange])

  function chooseMeasure(name: string) {
    const measure = measures.find((item) => item.name === name)
    if (measure === undefined) return
    const quantity = value.quantity ?? 1
    setWeighed(false)
    onChange({ measure_name: name, quantity, grams: quantity * measure.grams })
  }

  function chooseQuantity(quantity: number) {
    setWeighed(false)
    onChange({
      measure_name: value.measure_name,
      quantity,
      grams: selected ? quantity * selected.grams : value.grams,
    })
  }

  function overrideAbsolute(raw: string) {
    const parsed = Number.parseFloat(raw)
    setWeighed(true)
    // A weighed portion stands on its own — keeping a stale "½ bowl" beside a
    // number the user typed would misdescribe what they logged.
    onChange({
      measure_name: null,
      quantity: null,
      grams: Number.isFinite(parsed) && parsed > 0 ? parsed : null,
    })
  }

  if (isPending && foodId !== null) {
    return <p className="mb-4 text-sm text-text-muted">Loading measures…</p>
  }

  const unit = selected?.unit ?? 'g'

  return (
    <>
      <div className="mb-1 flex gap-2">
        <div className="w-24">
          <Field label="How much">
            {(props) => (
              <Select
                {...props}
                value={String(value.quantity ?? 1)}
                onChange={(event) => chooseQuantity(Number(event.target.value))}
                disabled={weighed}
              >
                {QUANTITIES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>

        <div className="flex-1">
          <Field label="Measure">
            {(props) => (
              <Select
                {...props}
                value={value.measure_name ?? ''}
                onChange={(event) => chooseMeasure(event.target.value)}
              >
                {weighed && <option value="">Weighed</option>}
                {measures.map((measure) => (
                  <option key={measure.name} value={measure.name}>
                    {measure.name}
                    {measure.is_approximate ? ' (approx.)' : ''}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
      </div>

      <Field
        label={`Or weigh it (${unit})`}
        hint={
          selected?.is_approximate
            ? 'This measure’s weight is a general figure, not one measured for this food — the entry will be marked estimated. Weighing it is exact.'
            : 'Filled in from the measure above. Change it only if you weighed the portion.'
        }
      >
        {(props) => (
          <NumberInput
            {...props}
            value={value.grams === null ? '' : String(Math.round(value.grams))}
            onChange={(event) => overrideAbsolute(event.target.value)}
          />
        )}
      </Field>

      {value.grams !== null && value.measure_name !== null && (
        <p className="-mt-2 mb-4 text-xs text-text-muted">
          {quantityLabel(value.quantity)} {value.measure_name} ·{' '}
          {formatAmount(value.grams, 'g')} {unit}
        </p>
      )}
    </>
  )
}
