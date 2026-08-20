import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatAmount } from '../lib/format'
import { SLOT_LABELS } from '../log/types'
import type { Diary, DiarySlotState } from '../log/types'
import { Badge } from '../ui/Badge'
import { Card, CardTitle } from '../ui/Card'

function SlotRow({ slot }: { slot: DiarySlotState }) {
  const kcal = slot.entries.reduce((total, entry) => total + entry.energy_kcal, 0)

  return (
    <li className="border-b border-border px-3 py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{SLOT_LABELS[slot.slot]}</span>
        <span className="text-xs text-text-muted">{slot.time}</span>
      </div>

      {slot.state === 'logged' && (
        <ul className="mt-1.5 space-y-1">
          {slot.entries.map((entry) => (
            <li key={entry.id} className="flex items-center gap-2 text-sm text-text-muted">
              {/*
                Both units, always: the household measure is what the user
                recognises, the absolute is what the nutrients were costed
                against. Either alone leaves a question unanswered.
              */}
              <span className="min-w-0 flex-1 truncate">
                {entry.name} · {entry.portion}
                {entry.grams !== null && entry.measure_name !== null && (
                  <span className="text-text-muted"> ({formatAmount(entry.grams, 'g')} g)</span>
                )}
              </span>
              {entry.is_estimated && <Badge tone="estimated">Estimated</Badge>}
              <span className="shrink-0 text-xs">{formatAmount(entry.energy_kcal, 'kcal')} kcal</span>
            </li>
          ))}
          <li className="pt-0.5 text-xs text-text-muted">
            {formatAmount(kcal, 'kcal')} kcal in this slot
          </li>
        </ul>
      )}

      {slot.state === 'skipped' && (
        <p className="mt-1 text-sm text-text-muted">
          <span className="text-text-muted">Skipped</span> — the mid-morning snack is optional.
        </p>
      )}

      {slot.state === 'empty' && (
        <Link
          to={`/log?slot=${slot.slot}`}
          className="mt-1.5 inline-flex min-h-11 items-center gap-1.5 text-sm text-accent"
        >
          <Plus className="size-4" aria-hidden="true" />
          Log {SLOT_LABELS[slot.slot].toLowerCase()}
        </Link>
      )}
    </li>
  )
}

export function MealSlotList({ diary }: { diary: Diary }) {
  return (
    <Card className="p-0">
      <div className="border-b border-border px-3 py-3">
        <CardTitle>Today’s meals</CardTitle>
      </div>
      <ul>
        {diary.slots.map((slot) => (
          <SlotRow key={slot.slot} slot={slot} />
        ))}
      </ul>
    </Card>
  )
}
