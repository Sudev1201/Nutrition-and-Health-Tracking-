import { useState } from 'react'
import { Leaf, Lock, LockOpen, RefreshCw, Shuffle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { cx } from '../lib/cx'
import { SLOT_LABELS } from '../log/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { CardTitle } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { SegmentedControl } from '../ui/SegmentedControl'
import { CookingView } from './CookingView'
import type { PlanDay, PlanItem } from './types'
import { useRegenerateWeek, useSwapItem, useToggleLock, useWeekPlan, weekStartIso } from './usePlan'

/**
 * `regenerating`: a regenerate replaces every unlocked item, so a swap or lock
 * sent meanwhile targets a row that is being replaced, and the server answers
 * 500. Both wait for it.
 */
function ItemRow({ item, regenerating }: { item: PlanItem; regenerating: boolean }) {
  const toggleLock = useToggleLock()
  const swap = useSwapItem()

  return (
    <li className="border-b border-border px-3 py-3 last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs text-text-muted">{SLOT_LABELS[item.slot]}</span>
        {item.locked && <Badge tone="accent">Locked</Badge>}
      </div>

      <p className="mt-0.5 text-sm font-medium">{item.dish_name}</p>
      <p className="text-xs text-text-muted">{item.portion}</p>

      {item.rationale !== null && (
        <p className="mt-1 text-xs text-text-muted italic">{item.rationale}</p>
      )}

      <div className="mt-2 flex gap-2">
        <Button
          variant="quiet"
          className="min-h-9 px-2 text-xs"
          disabled={item.locked || swap.isPending || regenerating}
          onClick={() => swap.mutate(item.id)}
        >
          <Shuffle className="size-3.5" aria-hidden="true" />
          Swap
        </Button>
        <Button
          variant="quiet"
          className="min-h-9 px-2 text-xs"
          disabled={toggleLock.isPending || regenerating}
          onClick={() => toggleLock.mutate({ itemId: item.id, locked: !item.locked })}
        >
          {item.locked ? (
            <LockOpen className="size-3.5" aria-hidden="true" />
          ) : (
            <Lock className="size-3.5" aria-hidden="true" />
          )}
          {item.locked ? 'Unlock' : 'Lock'}
        </Button>
      </div>
    </li>
  )
}

/**
 * One day of the plan, as a landmark region so the week is navigable by day for
 * a screen-reader user rather than being one undifferentiated list.
 */
function DayPanel({
  day,
  hiddenOnPhone,
  regenerating,
}: {
  day: PlanDay
  hiddenOnPhone: boolean
  regenerating: boolean
}) {
  return (
    <section
      aria-label={day.weekday}
      className={cx(
        'overflow-hidden rounded-card border border-border bg-surface',
        // Every day is rendered once and laid out by CSS. The phone shows the
        // selected day only; from `lg` the whole week sits side by side.
        hiddenOnPhone && 'hidden lg:block',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-3">
        <CardTitle>{day.weekday}</CardTitle>
        {day.vegetarian && (
          <span className="inline-flex items-center gap-1.5 text-xs text-on-target">
            <Leaf className="size-3.5" aria-hidden="true" />
            Vegetarian — {day.vegetarian_reason}
          </span>
        )}
      </div>
      {day.items.length === 0 ? (
        <p className="px-3 py-3 text-sm text-text-muted">Nothing planned for this day.</p>
      ) : (
        <ul>
          {day.items.map((item) => (
            <ItemRow key={item.id} item={item} regenerating={regenerating} />
          ))}
        </ul>
      )}
    </section>
  )
}

export function PlanScreen() {
  const start = weekStartIso()
  const plan = useWeekPlan(start)
  const regenerate = useRegenerateWeek()
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  if (plan.isPending) return <Skeleton className="h-96 w-full" />

  /*
   * A 404 from /plan/week means there is no profile yet: a plan is built from
   * the daily targets, and there are none to build from. Point at onboarding
   * rather than reporting an error that did not happen.
   */
  if (plan.error instanceof ApiError && plan.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description="A meal plan is built from your daily targets, so there is nothing to plan until you have told us about yourself."
        action={
          <Link
            to="/profile/about"
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface"
          >
            Set up your profile
          </Link>
        }
      />
    )
  }
  if (plan.isError || plan.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your plan could not be loaded. Please try again.
      </p>
    )
  }

  const days = plan.data.days
  const active = days.find((day) => day.date === selectedDate) ?? days[0]

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {/*
          A phone shows one day at a time behind this picker; from `lg` the whole
          week is laid out as columns below and the picker becomes redundant.
        */}
        {/*
          Seven full weekday names do not fit across a 390px phone — the picker
          ran off the edge with Friday and Saturday unreachable. Abbreviated here
          and allowed to scroll, so every day is reachable at any width.
        */}
        <div className="-mx-4 max-w-full overflow-x-auto px-4 lg:hidden">
          <SegmentedControl
            label="Day"
            value={active.date}
            onChange={setSelectedDate}
            options={days.map((day) => ({
              value: day.date,
              label: day.weekday.slice(0, 3),
              a11yLabel: day.weekday,
            }))}
          />
        </div>

        <Button
          className="ml-auto"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate(start)}
        >
          <RefreshCw className="size-4" aria-hidden="true" />
          Regenerate week
        </Button>
      </div>

      <CookingView date={active.date} weekday={active.weekday} />

      <div className="grid gap-3 lg:grid-cols-7">
        {days.map((day) => (
          <DayPanel
            key={day.date}
            day={day}
            hiddenOnPhone={day.date !== active.date}
            regenerating={regenerate.isPending}
          />
        ))}
      </div>
    </section>
  )
}
