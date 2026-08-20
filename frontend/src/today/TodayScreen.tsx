import { AlertTriangle, Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { Card, CardTitle } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { NutrientBar } from '../ui/NutrientBar'
import { StatTile } from '../ui/StatTile'
import { BaselineNote } from './BaselineNote'
import { MealSlotList } from './MealSlotList'
import { todayIso, useDiary, useTodayTargets } from './useToday'
import type { NutrientProgress, TodayWarning } from './types'

function WarningNote({ warning }: { warning: TodayWarning }) {
  const conflict = warning.kind === 'condition-conflict'
  const Icon = conflict ? AlertTriangle : Info

  return (
    <li
      className={
        conflict
          ? 'flex gap-2 rounded-card border border-above-limit/40 bg-above-limit/5 p-3 text-sm text-above-limit'
          : 'flex gap-2 rounded-card border border-border bg-surface p-3 text-sm text-text-muted'
      }
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{warning.message}</span>
    </li>
  )
}

function nutrientBarProps(nutrient: NutrientProgress) {
  return {
    name: nutrient.display_name,
    unit: nutrient.unit,
    consumed: nutrient.consumed,
    target: nutrient.target_effective,
    ear: nutrient.ear,
    tul: nutrient.tul,
    kind: nutrient.kind,
    carriedIn: nutrient.carried_in,
    carriedFrom: nutrient.carried_from ?? undefined,
  }
}

export function TodayScreen() {
  const date = todayIso()
  const targets = useTodayTargets(date)
  const diary = useDiary(date)

  if (targets.isPending || diary.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  /*
   * A 404 from /targets/today is not a failure: the backend answers that way
   * when there is no profile, because nothing can be computed without one. The
   * user simply has not onboarded, so this points them at it rather than
   * apologising for an error that did not happen.
   */
  if (targets.error instanceof ApiError && targets.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description="Your daily targets are computed from your age, weight, activity and any health conditions — so there is nothing to show until you have told us about yourself."
        action={
          <Link
            to="/profile"
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface"
          >
            Set up your profile
          </Link>
        }
      />
    )
  }

  if (targets.isError || diary.isError || targets.data === undefined || diary.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Today’s figures could not be loaded. Please try again.
      </p>
    )
  }

  const { nutrients, warnings } = targets.data
  const macros = nutrients.filter((nutrient) => nutrient.category === 'macro')
  const micros = nutrients.filter((nutrient) => nutrient.category !== 'macro')

  return (
    <section>
      <BaselineNote date={date} />

      {warnings.length > 0 && (
        <ul className="mb-4 space-y-2">
          {warnings.map((warning) => (
            <WarningNote key={warning.kind} warning={warning} />
          ))}
        </ul>
      )}

      {/*
        Two columns from `lg` up so a wide screen reads as a dashboard rather than
        a stretched phone view: figures on the left, the day's meals beside them.
      */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {macros.map((nutrient) => (
              <StatTile
                key={nutrient.code}
                label={nutrient.display_name}
                consumed={nutrient.consumed}
                target={nutrient.target_effective}
                unit={nutrient.unit}
                ear={nutrient.ear}
                tul={nutrient.tul}
                kind={nutrient.kind}
              />
            ))}
          </div>

          <Card>
            <CardTitle>Vitamins and minerals</CardTitle>
            <div className="mt-1 divide-y divide-border">
              {micros.map((nutrient) => (
                <NutrientBar key={nutrient.code} {...nutrientBarProps(nutrient)} />
              ))}
            </div>
          </Card>
        </div>

        <MealSlotList diary={diary.data} />
      </div>
    </section>
  )
}
