import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError } from '../lib/api'
import { formatAmount, formatDay } from '../lib/format'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Field, NumberInput, TextInput } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import { useAddWeighIn, useRemoveWeighIn, useWeight } from './useWeight'
import type { WeightTrend } from './types'

// The profile's bounds. The energy equations are weight-based, so a typo here
// would quietly skew every target.
const MIN_KG = 20
const MAX_KG = 300

/** "losing about 0.3 kg a week", for a goal or an observed trend. */
function rateWords(kgPerWeek: number): string {
  if (Math.abs(kgPerWeek) < 0.05) return 'holding steady'
  const direction = kgPerWeek < 0 ? 'losing' : 'gaining'
  return `${direction} about ${Math.abs(kgPerWeek).toFixed(1)} kg a week`
}

function WeighInForm() {
  const addWeighIn = useAddWeighIn()
  const [entry, setEntry] = useState('')
  // Blurred once: "7" is on its way to "74", so the range error waits for it.
  const [touched, setTouched] = useState(false)
  // null is the user's today, which the server decides -- a browser in another
  // timezone, or a screen left open past midnight, would send the wrong day. Only
  // a day the user picked is sent.
  const [date, setDate] = useState<string | null>(null)
  const today = todayIso()

  const parsed = Number.parseFloat(entry)
  const valid = Number.isFinite(parsed) && parsed > MIN_KG && parsed <= MAX_KG
  const invalid = entry.trim() !== '' && !valid

  return (
    <Card>
      <CardTitle>Add this week’s weigh-in</CardTitle>
      <div className="mt-2 grid gap-x-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field
          label="Weight in kg"
          error={
            touched && invalid
              ? `Please give a weight in kg between ${MIN_KG} and ${MAX_KG}.`
              : undefined
          }
        >
          {(fieldProps) => (
            <NumberInput
              {...fieldProps}
              value={entry}
              onChange={(event) => setEntry(event.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="74.2"
            />
          )}
        </Field>
        <Field label="Date">
          {(fieldProps) => (
            <TextInput
              {...fieldProps}
              type="date"
              value={date ?? today}
              max={today}
              onChange={(event) =>
                setDate(event.target.value === todayIso() ? null : event.target.value)
              }
            />
          )}
        </Field>
        <Button
          variant="primary"
          className="mb-4"
          disabled={!valid || date === '' || addWeighIn.isPending}
          onClick={() =>
            addWeighIn.mutate(date === null ? { weight_kg: parsed } : { weight_kg: parsed, date }, {
              // Reset only once saved, so a failed save does not lose what was typed.
              // The date goes back to today: a back-dated day that stuck would make
              // the next weigh-in overwrite it, and never read the trend.
              onSuccess: () => {
                setEntry('')
                setTouched(false)
                setDate(null)
              },
            })
          }
        >
          Save
        </Button>
      </div>
      {addWeighIn.isError && (
        <p role="alert" className="mb-2 text-sm text-above-limit">
          That weigh-in could not be saved. Please try again.
        </p>
      )}
      <p className="text-xs text-text-muted">
        Weekly is enough. The trend is read across several weigh-ins, so a day of water weight
        doesn’t trigger a calorie recalibration. A missed week can be filled in by changing
        the date.
      </p>
    </Card>
  )
}

function Summary({ data }: { data: WeightTrend }) {
  return (
    <Card>
      <CardTitle>Where you are</CardTitle>
      <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-text-muted">Smoothed weight</dt>
          <dd className="font-medium">
            {data.smoothed_kg === null ? 'No weigh-ins yet' : `${data.smoothed_kg} kg`}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Your goal</dt>
          <dd className="font-medium">{rateWords(data.expected_kg_per_week)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Recent trend</dt>
          <dd className="font-medium">
            {data.observed_kg_per_week === null
              ? 'Not enough weigh-ins yet'
              : rateWords(data.observed_kg_per_week)}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Calorie target</dt>
          <dd className="font-medium">{formatAmount(data.calorie_target_kcal, 'kcal')} kcal a day</dd>
        </div>
      </dl>
      {data.note !== null && <p className="mt-3 text-sm text-text-muted">{data.note}</p>}
    </Card>
  )
}

function Adjustment({ data }: { data: WeightTrend }) {
  if (data.adjustment === null) return null
  const { delta_kcal: delta, since, reason } = data.adjustment

  return (
    <Card>
      <CardTitle>Your calorie target moved</CardTitle>
      <p className="mt-1 text-sm">
        <strong className="font-medium">
          {delta > 0 ? '+' : ''}
          {delta} kcal
        </strong>{' '}
        since {formatDay(since)}.
      </p>
      <p className="mt-1 text-sm text-text-muted">{reason}</p>
    </Card>
  )
}

function TrendChart({ data }: { data: WeightTrend }) {
  return (
    <Card>
      <CardTitle>Trend</CardTitle>
      {data.weigh_ins.length < 2 ? (
        <p className="mt-2 text-sm text-text-muted">
          Your trend line appears after your second weigh-in.
        </p>
      ) : (
        // The list beside it carries the same figures for screen readers.
        <div className="mt-2 h-56 w-full" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.weigh_ins} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(iso: string) => formatDay(iso)}
                tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
                stroke="var(--color-border)"
              />
              <YAxis
                domain={['dataMin - 1', 'dataMax + 1']}
                tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 6,
                  color: 'var(--color-text)',
                }}
              />
              <Line
                type="monotone"
                dataKey="weight_kg"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function WeighInList({ data }: { data: WeightTrend }) {
  const remove = useRemoveWeighIn()
  const newestFirst = [...data.weigh_ins].reverse()

  return (
    <Card>
      <CardTitle>Weigh-ins</CardTitle>
      {newestFirst.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">No weigh-ins yet.</p>
      ) : (
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Every weigh-in, newest first</caption>
          <tbody className="divide-y divide-border">
            {newestFirst.map((weighIn) => (
              <tr key={weighIn.date}>
                <th scope="row" className="py-2 text-left font-normal">
                  {formatDay(weighIn.date)}
                </th>
                <td className="py-2">{weighIn.weight_kg} kg</td>
                <td className="py-2 text-right">
                  <Button
                    variant="quiet"
                    aria-label={`Remove the weigh-in on ${formatDay(weighIn.date)}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(weighIn.date)}
                  >
                    Remove
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          That weigh-in could not be removed. Please try again.
        </p>
      )}
    </Card>
  )
}

export function WeightScreen() {
  const weight = useWeight()

  if (weight.isPending) return <Skeleton className="h-64 w-full" />

  // A 404 means there is no profile yet: the trend starts from the profile's weight.
  if (weight.error instanceof ApiError && weight.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your targets"
        description="Your weight trend starts from the weight in your profile, so there is nothing to show until you have told us about yourself."
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
  if (weight.isError || weight.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your weight history could not be loaded. Please try again.
      </p>
    )
  }

  const data = weight.data
  return (
    <section className="space-y-4">
      <WeighInForm />
      <Summary data={data} />
      <Adjustment data={data} />
      <div className="grid gap-4 lg:grid-cols-2">
        <TrendChart data={data} />
        <WeighInList data={data} />
      </div>
    </section>
  )
}
