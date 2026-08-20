import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../lib/api'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Field, NumberInput } from '../ui/fields'
import { DemoDataBanner, Skeleton } from '../ui/feedback'
import type { WeightTrend } from './types'

function useWeight() {
  return useQuery({
    queryKey: ['weight'],
    queryFn: () => api.get<WeightTrend>('/weight'),
    retry: false,
  })
}

function useAddWeighIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (weightKg: number) => api.post('/weight', { weight_kg: weightKg }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['weight'] })
      // A recalibrated calorie target changes today's figures too.
      queryClient.invalidateQueries({ queryKey: ['targets'] })
    },
  })
}

export function WeightScreen() {
  const weight = useWeight()
  const addWeighIn = useAddWeighIn()
  const [entry, setEntry] = useState('')

  if (weight.isPending) return <Skeleton className="h-64 w-full" />
  if (weight.isError || weight.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your weight history could not be loaded. Please try again.
      </p>
    )
  }

  const data = weight.data
  const parsed = Number.parseFloat(entry)
  const canSubmit = Number.isFinite(parsed) && parsed > 0

  return (
    <section className="space-y-4">
      <DemoDataBanner endpoint="GET /weight" />

      <Card>
        <CardTitle>Add this week’s weigh-in</CardTitle>
        <div className="mt-2 flex items-end gap-3">
          <div className="flex-1">
            <Field label="Weight in kg">
              {(fieldProps) => (
                <NumberInput
                  {...fieldProps}
                  value={entry}
                  onChange={(event) => setEntry(event.target.value)}
                  placeholder="74.2"
                />
              )}
            </Field>
          </div>
          <Button
            variant="primary"
            className="mb-4"
            disabled={!canSubmit || addWeighIn.isPending}
            onClick={() => {
              addWeighIn.mutate(parsed)
              setEntry('')
            }}
          >
            Save
          </Button>
        </div>
        <p className="text-xs text-text-muted">
          Weekly is enough. The trend is smoothed across the last few weigh-ins so a day of
          water weight doesn’t move your targets.
        </p>
      </Card>

      <Card>
        <CardTitle>Trend</CardTitle>
        <div className="mt-2 h-56 w-full" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.weigh_ins} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--color-border)" vertical={false} />
              <XAxis
                dataKey="date"
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

        <table className="sr-only">
          <caption>Weight at each weigh-in</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Weight</th>
            </tr>
          </thead>
          <tbody>
            {data.weigh_ins.map((weighIn) => (
              <tr key={weighIn.date}>
                <th scope="row">{weighIn.date}</th>
                <td>{weighIn.weight_kg} kg</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {data.adjustment !== null && (
        <Card>
          <CardTitle>Your calorie target moved</CardTitle>
          <p className="mt-1 text-sm">
            <strong className="font-medium">
              {data.adjustment.delta_kcal > 0 ? '+' : ''}
              {data.adjustment.delta_kcal} kcal
            </strong>{' '}
            — now {data.calorie_target_kcal} kcal a day.
          </p>
          <p className="mt-1 text-sm text-text-muted">{data.adjustment.reason}</p>
        </Card>
      )}
    </section>
  )
}
