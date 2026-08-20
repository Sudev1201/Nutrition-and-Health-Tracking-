import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { cx } from '../lib/cx'
import { formatAmount, formatPercent, formatWithUnit, unitLabel } from '../lib/format'
import { nutrientStatus } from '../lib/status'
import { weekStartIso } from '../plan/usePlan'
import { Card, CardTitle } from '../ui/Card'
import { DemoDataBanner, Skeleton } from '../ui/feedback'
import { STATUS_LABELS, STATUS_TEXT } from '../ui/statusPresentation'
import { EnergyChart } from './EnergyChart'
import type { WeeklyReport } from './types'

function useWeeklyReport(start: string) {
  return useQuery({
    queryKey: ['reports', 'week', start],
    queryFn: () => api.get<WeeklyReport>(`/reports/week?start=${start}`),
    retry: false,
  })
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-0.5 text-xl font-semibold">{value}</p>
      {hint !== undefined && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}

export function ReportScreen() {
  const start = weekStartIso()
  const report = useWeeklyReport(start)

  if (report.isPending) return <Skeleton className="h-96 w-full" />
  if (report.isError || report.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your report could not be loaded. Please try again.
      </p>
    )
  }

  const data = report.data
  const totalKcal = data.measured_kcal + data.estimated_kcal
  const estimatedShare = formatPercent(data.estimated_kcal, totalKcal)

  return (
    <section className="space-y-4">
      <DemoDataBanner endpoint="GET /reports/week" />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Figure
          label="Slots logged"
          value={`${data.slots_logged} of ${data.slots_total}`}
          hint="across the week"
        />
        <Figure
          label="Measured"
          value={`${formatAmount(data.measured_kcal, 'kcal')} kcal`}
          hint="weighed or by household measure"
        />
        <Figure
          label="Estimated"
          value={`${formatAmount(data.estimated_kcal, 'kcal')} kcal`}
          hint={`${estimatedShare}% of the week — shown separately`}
        />
        <Figure
          label="Shortfalls not made up"
          value={String(data.uncompensated.length)}
          hint="see below"
        />
      </div>

      <Card>
        <CardTitle>Energy each day</CardTitle>
        <div className="mt-2">
          <EnergyChart days={data.days} />
        </div>
      </Card>

      <Card className="overflow-x-auto p-0">
        <div className="border-b border-border px-4 py-3">
          <CardTitle>Nutrients across the week</CardTitle>
        </div>
        <table className="w-full text-sm">
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
            {data.nutrients.map((nutrient) => {
              // Judged on the week's totals, against the week's summed reference
              // figures -- the DRI framework's own "average over 1 or more weeks".
              const status = nutrientStatus({
                consumed: nutrient.consumed_total,
                ear: nutrient.ear === null ? null : nutrient.ear * 7,
                rda: nutrient.target_total,
                tul: nutrient.tul === null ? null : nutrient.tul * 7,
                kind: nutrient.kind,
              })

              return (
                <tr key={nutrient.code} className="border-b border-border last:border-b-0">
                  <th scope="row" className="px-4 py-2 text-left font-medium">
                    {nutrient.display_name}
                  </th>
                  <td className="px-4 py-2 text-right">
                    {formatAmount(nutrient.consumed_total, nutrient.unit)}
                  </td>
                  <td className="px-4 py-2 text-right text-text-muted">
                    {formatAmount(nutrient.target_total, nutrient.unit)}{' '}
                    {unitLabel(nutrient.unit)}
                  </td>
                  <td className="px-4 py-2 text-right">{nutrient.days_met} of 7</td>
                  <td className={cx('px-4 py-2', STATUS_TEXT[status])}>
                    {STATUS_LABELS[status]}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>

      <Card>
        <CardTitle>What could not be made up</CardTitle>
        <ul className="mt-2 space-y-3">
          {data.uncompensated.map((gap) => (
            <li key={gap.code} className="text-sm">
              <span className="font-medium">
                {gap.display_name} — {formatWithUnit(gap.amount, gap.unit)}
              </span>
              <p className="text-text-muted">{gap.reason}</p>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardTitle>What to eat next week</CardTitle>
        <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-text-muted">
          {data.suggestions.map((suggestion) => (
            <li key={suggestion}>{suggestion}</li>
          ))}
        </ul>
      </Card>
    </section>
  )
}
