import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { formatAmount, formatDay, formatPercent, formatWithUnit, unitLabel } from '../lib/format'
import { nutrientStatus } from '../lib/status'
import { weekStartIso } from '../plan/usePlan'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { STATUS_LABELS, STATUS_TEXT } from '../ui/statusPresentation'
import { EnergyChart } from './EnergyChart'
import type {
  ReportNutrient,
  ReportStatus,
  Suggestion,
  UncompensatedGap,
  WeeklyReport,
} from './types'
import { addDays, lastCompleteWeekStart, useWeeklyReport } from './useReport'

const PROFILE_LINK = [
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent',
  'px-4 text-sm font-medium text-surface',
].join(' ')

// Below this, a figure speaks for only part of what was eaten, and the table says
// so. It is the threshold Today's bars use.
const FULL_COVERAGE = 0.995

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold">{value}</p>
      {hint !== undefined && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}

function WeekHeader({
  start,
  status,
  onMove,
}: {
  start: string
  status: ReportStatus | undefined
  onMove: (start: string) => void
}) {
  // The server refuses a week that has not started, so Next stops at this one.
  const atCurrentWeek = start >= weekStartIso()

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* Worked out from the week asked for, so it shows while the report loads. */}
        <h2 className="text-xl font-semibold">
          {`${formatDay(start)} – ${formatDay(addDays(start, 6))}`}
        </h2>
        {status === 'in-progress' && <Badge tone="accent">In progress</Badge>}
      </div>
      <div className="flex gap-2">
        <Button onClick={() => onMove(addDays(start, -7))}>
          <ChevronLeft className="size-4" aria-hidden="true" />
          Previous week
        </Button>
        <Button disabled={atCurrentWeek} onClick={() => onMove(addDays(start, 7))}>
          Next week
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  )
}

function overLimitWords(days: number): string {
  return days === 1 ? '1 day over the limit' : `${days} days over the limit`
}

function NutrientRow({ nutrient }: { nutrient: ReportNutrient }) {
  /*
   * The week's intake against its summed EAR and target: the DRI framework's own
   * "average daily intake over 1 or more weeks". A daily upper limit is never
   * summed into a weekly one, so it is left out here, and the days past it are
   * counted on their own. A ceiling's own figure is its limit, so as a fallback
   * (below) a ceiling's week is set against its summed ceilings, but that summed
   * standing is overridden the moment even one measured day went over.
   */
  let status = nutrientStatus({
    consumed: nutrient.consumed_total,
    ear: nutrient.ear_total,
    rda: nutrient.target_total,
    tul: null,
    kind: nutrient.kind,
  })

  /*
   * `days_over_limit` counts TUL crossings only (see types.ts), so it is always 0
   * for a ceiling -- sodium has no TUL -- and never says anything about a ceiling
   * nutrient going over. A ceiling's own daily figure IS its limit, so a day it
   * was not met (consumed at or past the effective ceiling -- exactly Today's
   * "above the limit", `summary.is_met`) is a day over the limit. Good days in the
   * same week must not average that away into an "on target" reading.
   */
  const overLimitDays =
    nutrient.kind === 'ceiling'
      ? nutrient.measured_days - nutrient.days_met
      : nutrient.days_over_limit
  if (nutrient.kind === 'ceiling' && overLimitDays > 0) status = 'above-limit'

  return (
    <tr className="border-b border-border last:border-b-0">
      <th scope="row" className="px-4 py-2 text-left font-medium">
        {nutrient.display_name}
      </th>
      <td className="px-4 py-2 text-right">
        {formatAmount(nutrient.consumed_total, nutrient.unit)}
      </td>
      <td className="px-4 py-2 text-right text-text-muted">
        {formatAmount(nutrient.target_total, nutrient.unit)} {unitLabel(nutrient.unit)}
      </td>
      <td className="px-4 py-2 text-right">
        {nutrient.days_met} of {nutrient.measured_days}
      </td>
      <td className="px-4 py-2">
        <span className={STATUS_TEXT[status]}>{STATUS_LABELS[status]}</span>
        {overLimitDays > 0 && (
          <span className="block text-xs text-above-limit">{overLimitWords(overLimitDays)}</span>
        )}
        {/*
          Partial coverage is reported rather than hidden, as on Today. The total
          speaks only for the food that carried a figure.
        */}
        {nutrient.coverage < FULL_COVERAGE && (
          <span className="block text-xs text-text-muted">
            {`Measured for ${Math.round(nutrient.coverage * 100)}% of what you ate`}
          </span>
        )}
      </td>
    </tr>
  )
}

function NutrientTable({ nutrients }: { nutrients: ReportNutrient[] }) {
  return (
    <Card className="overflow-x-auto p-0">
      <div className="border-b border-border px-4 py-3">
        <CardTitle>Nutrients across the week</CardTitle>
        <p className="mt-1 text-xs text-text-muted">
          Each total counts only the days your food carried a figure for it, so a gap in the
          food tables never reads as a shortfall.
        </p>
      </div>
      <table className="w-full text-sm">
        <caption className="sr-only">Nutrients across the week</caption>
        <thead>
          <tr className="border-b border-border text-left text-xs text-text-muted">
            <th scope="col" className="px-4 py-2 font-medium">Nutrient</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Intake</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Target</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Days met</th>
            <th scope="col" className="px-4 py-2 font-medium">Standing</th>
          </tr>
        </thead>
        <tbody>
          {nutrients.map((nutrient) => (
            <NutrientRow key={nutrient.code} nutrient={nutrient} />
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function Uncompensated({ gaps }: { gaps: UncompensatedGap[] }) {
  return (
    <Card>
      <CardTitle>What could not be made up</CardTitle>
      {gaps.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">No shortfall expired this week.</p>
      ) : (
        <ul className="mt-2 space-y-3">
          {gaps.map((gap) => (
            <li key={gap.code} className="text-sm">
              <span className="font-medium">
                {gap.display_name} — {formatWithUnit(gap.amount, gap.unit)}
              </span>
              <p className="text-text-muted">{gap.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Suggestions({ suggestions }: { suggestions: Suggestion[] }) {
  return (
    <Card>
      <CardTitle>What to eat next week</CardTitle>
      {suggestions.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">
          No nutrient fell short on enough measured days to suggest a change.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs text-text-muted">
            Dishes your plan can serve, that suit your diet and leave out the foods you avoid.
          </p>
          <ul className="mt-3 space-y-3">
            {suggestions.map((suggestion) => (
              <li key={suggestion.nutrient_code} className="text-sm">
                <p>{suggestion.text}</p>
                {suggestion.foods.length > 0 && (
                  <ul
                    aria-label={`Dishes for ${suggestion.display_name}`}
                    className="mt-1.5 flex flex-wrap gap-1.5"
                  >
                    {suggestion.foods.map((food) => (
                      <li key={food.food_id}>
                        <Badge tone="accent">{food.name}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

function ReportBody({ data }: { data: WeeklyReport }) {
  const inProgress = data.status === 'in-progress'

  if (data.tracked_days === 0) {
    return inProgress ? (
      <EmptyState
        title="Nothing to add up yet"
        description="A day counts here once it is over and something was logged in it."
      />
    ) : (
      <EmptyState
        title="Nothing was logged this week"
        description={
          'A day with nothing logged is left out of every total, rather than read as a ' +
          'day of eating nothing.'
        }
      />
    )
  }

  // The days that have ended. A day in progress, or still to come, counts in nothing.
  const elapsed = data.days.filter(
    (day) => day.state === 'tracked' || day.state === 'untracked',
  ).length
  const { logged, skipped, expected } = data.slots
  const estimatedShare = formatPercent(
    data.estimated_kcal,
    data.measured_kcal + data.estimated_kcal,
  )

  return (
    <>
      {inProgress && (
        <p className="text-sm text-text-muted">
          This week is still going. Today and the days after it count once they are over.
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
        <Figure
          label="Days logged"
          value={`${data.tracked_days} of ${elapsed}`}
          hint={inProgress ? 'days over so far' : 'across the week'}
        />
        <Figure
          label="Meals accounted for"
          value={`${logged + skipped} of ${expected}`}
          hint={`${logged} logged, ${skipped} skipped, ${expected - logged - skipped} missed`}
        />
        <Figure
          label="Measured"
          value={`${formatAmount(data.measured_kcal, 'kcal')} kcal`}
          hint="weighed or by household measure"
        />
        <Figure
          label="Estimated"
          value={`${formatAmount(data.estimated_kcal, 'kcal')} kcal`}
          hint={`${estimatedShare}% of the week’s energy, kept apart`}
        />
        {data.plan !== null && (
          <Figure
            label="Plan followed"
            value={`${data.plan.followed} of ${data.plan.planned}`}
            hint="planned meals eaten as planned"
          />
        )}
      </div>

      <Card>
        <CardTitle>Energy each day</CardTitle>
        <div className="mt-2">
          <EnergyChart days={data.days} />
        </div>
      </Card>

      <NutrientTable nutrients={data.nutrients} />
      <Uncompensated gaps={data.uncompensated} />
      <Suggestions suggestions={data.suggestions} />
    </>
  )
}

function WeekContent({ report }: { report: ReturnType<typeof useWeeklyReport> }) {
  if (report.isPending) return <Skeleton className="h-96 w-full" />

  // Only when this browser's calendar has reached a Sunday that the account's
  // timezone has not: the server counts weeks where the account is.
  if (report.error instanceof ApiError && report.error.status === 422) {
    return (
      <EmptyState
        title="That week has not started yet"
        description={
          'Weeks begin on Sunday in your account’s timezone, where it is still the ' +
          'week before.'
        }
      />
    )
  }
  if (report.isError || report.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        This week’s report could not be loaded. Please try again.
      </p>
    )
  }
  return <ReportBody data={report.data} />
}

export function ReportScreen() {
  const [start, setStart] = useState(() => lastCompleteWeekStart())
  const report = useWeeklyReport(start)

  /*
   * A 404 means there is no profile yet: a report is measured against the daily
   * targets, and there are none. Point at onboarding rather than reporting an
   * error that did not happen.
   */
  if (report.error instanceof ApiError && report.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description={
          'Your weekly report is measured against your daily targets, so there is ' +
          'nothing to report until you have told us about yourself.'
        }
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }

  return (
    <section className="space-y-4">
      <WeekHeader start={start} status={report.data?.status} onMove={setStart} />
      <WeekContent report={report} />
    </section>
  )
}
