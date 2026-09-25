import { useState } from 'react'
import { useIsMutating } from '@tanstack/react-query'
import { Leaf, Lock, LockOpen, RefreshCw, Shuffle, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, errorDetail } from '../lib/api'
import { cx } from '../lib/cx'
import { SLOT_LABELS } from '../log/types'
import { useLlmSettings } from '../settings/useLlmSettings'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { CardTitle } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { SegmentedControl } from '../ui/SegmentedControl'
import { CookingView } from './CookingView'
import type { PlanDay, PlanItem } from './types'
import {
  usePolishWeek,
  useRegenerateWeek,
  useSwapItem,
  useToggleLock,
  useWeekPlan,
  weekStartIso,
} from './usePlan'

const POLISH_FAILED = 'The descriptions could not be added. Please try again.'

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

      {/*
        Claude's words sit beside the planner's and replace none of them: the dish
        and portion above, and the rationale below, render exactly as they do
        without a description.
      */}
      {item.description !== null && <p className="mt-1 text-xs">{item.description}</p>}

      {item.rationale !== null && (
        <p className="mt-1 text-xs text-text-muted italic">{item.rationale}</p>
      )}

      {item.cooking_note !== null && (
        <details className="mt-1 text-xs">
          <summary className="cursor-pointer py-1 text-text-muted">Cooking tip</summary>
          <p>{item.cooking_note}</p>
        </details>
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
  const polish = usePolishWeek()
  const llm = useLlmSettings()
  // From the mutation cache, not this screen's own observer, so the lockout
  // holds when the user leaves the Plan screen mid-polish and comes back.
  const polishing = useIsMutating({ mutationKey: ['plan', 'polish'] }) > 0
  const regenerating = useIsMutating({ mutationKey: ['plan', 'regenerate'] }) > 0
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
  // Offered only with a key Anthropic accepted. A missing, refused or unreadable
  // key is put right on the AI descriptions screen, not here.
  const canPolish = llm.data?.available === true && llm.data.status === 'ok'
  // Each answer replaces the whole cached week, so whichever lands last wins: a
  // polish answered before a regenerate committed would put the old dishes back.
  const busy = regenerating || polishing

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

        <div className="ml-auto flex flex-wrap justify-end gap-2">
          {canPolish && (
            <Button disabled={busy} onClick={() => polish.mutate(start)}>
              <Sparkles className="size-4" aria-hidden="true" />
              {polishing ? 'Adding descriptions…' : 'Add descriptions'}
            </Button>
          )}
          <Button disabled={busy} onClick={() => regenerate.mutate(start)}>
            <RefreshCw className="size-4" aria-hidden="true" />
            Regenerate week
          </Button>
        </div>
      </div>

      {/*
        Outside the button's condition: a key Anthropic refused takes the button
        away, and the reason must stay on screen.
      */}
      {polish.isError && (
        <p role="alert" className="mb-4 text-sm text-above-limit">
          {errorDetail(polish.error, POLISH_FAILED)}
        </p>
      )}

      {/*
        A polish can succeed and describe nothing, and the week comes back as it
        was. Said quietly, so the click does not look as if nothing happened.
      */}
      {polish.isSuccess && polish.data.described === 0 && (
        <p role="status" className="mb-4 text-sm text-text-muted">
          Claude added no new descriptions this time.
        </p>
      )}

      <CookingView date={active.date} weekday={active.weekday} />

      <div className="grid gap-3 lg:grid-cols-7">
        {days.map((day) => (
          <DayPanel
            key={day.date}
            day={day}
            hiddenOnPhone={day.date !== active.date}
            // Read from the mutation cache, like the toolbar's own `regenerating`,
            // so Swap and Lock stay locked out consistently with Regenerate across
            // leaving the Plan screen mid-regenerate and coming back.
            regenerating={regenerating}
          />
        ))}
      </div>
    </section>
  )
}
