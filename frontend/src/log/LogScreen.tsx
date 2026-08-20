import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FoodSearchScreen } from '../foods/FoodSearchScreen'
import type { FoodResult } from '../foods/useFoodSearch'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Checkbox, Field, Select } from '../ui/fields'
import { Sheet } from '../ui/Sheet'
import { SLOT_LABELS, SLOT_ORDER } from './types'
import type { MealSlot } from './types'
import { PortionField } from './PortionField'
import { EMPTY_PORTION } from './portion'
import type { Portion } from './portion'
import { buildDiaryEntry, useLogMeal } from './useLogMeal'

function isMealSlot(value: string | null): value is MealSlot {
  return value !== null && (SLOT_ORDER as readonly string[]).includes(value)
}

export function LogScreen() {
  const [params] = useSearchParams()
  const slotFromLink = params.get('slot')

  const [slot, setSlot] = useState<MealSlot>(
    isMealSlot(slotFromLink) ? slotFromLink : 'breakfast',
  )
  const [selected, setSelected] = useState<FoodResult | null>(null)
  const [portion, setPortion] = useState<Portion>(EMPTY_PORTION)
  const [isEstimated, setIsEstimated] = useState(false)

  const logMeal = useLogMeal()

  function closeSheet() {
    setSelected(null)
    setPortion(EMPTY_PORTION)
    setIsEstimated(false)
  }

  function confirm() {
    if (selected === null) return

    logMeal.mutate(
      buildDiaryEntry({
        date: todayIso(),
        slot,
        foodId: selected.id,
        foodKind: selected.kind,
        portion,
        isEstimated,
      }),
      { onSuccess: closeSheet },
    )
  }

  return (
    <section>
      <Field label="Meal">
        {(fieldProps) => (
          <Select
            {...fieldProps}
            value={slot}
            onChange={(event) => setSlot(event.target.value as MealSlot)}
          >
            {SLOT_ORDER.map((value) => (
              <option key={value} value={value}>
                {SLOT_LABELS[value]}
              </option>
            ))}
          </Select>
        )}
      </Field>

      {/* The same search component the standalone food screen uses. */}
      <FoodSearchScreen onSelect={setSelected} />

      <Sheet
        open={selected !== null}
        title={selected?.name ?? ''}
        onClose={closeSheet}
      >
        <PortionField
          foodId={selected?.id ?? null}
          foodKind={selected?.kind ?? null}
          value={portion}
          onChange={setPortion}
        />

        <Checkbox
          label="This portion is an estimate"
          checked={isEstimated}
          onChange={(event) => setIsEstimated(event.target.checked)}
        />
        <p className="mt-1 mb-4 text-xs text-text-muted">
          Restaurant meals and eyeballed portions. The weekly report keeps these separate from
          what you measured, so a week eaten out isn't shown with false precision.
        </p>

        <Button
          variant="primary"
          block
          disabled={portion.grams === null || logMeal.isPending}
          onClick={confirm}
        >
          Add to {SLOT_LABELS[slot].toLowerCase()}
        </Button>

        {logMeal.isError && (
          <p role="alert" className="mt-2 text-sm text-above-limit">
            That could not be logged. Please try again.
          </p>
        )}
      </Sheet>
    </section>
  )
}
