import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatAmount } from '../lib/format'
import type { ReportDay } from './types'

/**
 * Energy for each day against the target line.
 *
 * Bars are coloured by the same status tokens the rest of the app uses, so a day
 * over target reads identically here and on Today. The chart is decorative for
 * assistive technology — `aria-hidden` — and the same numbers are published as a
 * real table beside it, because Recharts emits SVG with no text alternative.
 */
export function EnergyChart({ days }: { days: ReportDay[] }) {
  const target = days[0]?.target_kcal ?? 0

  return (
    <>
      <div className="h-56 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={days} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="weekday"
              tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
              stroke="var(--color-border)"
            />
            <YAxis
              tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
              stroke="var(--color-border)"
            />
            <Tooltip
              cursor={{ fill: 'var(--color-surface-alt)' }}
              contentStyle={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 6,
                color: 'var(--color-text)',
              }}
              formatter={(value) => [`${formatAmount(Number(value ?? 0), 'kcal')} kcal`, 'Energy']}
            />
            <ReferenceLine
              y={target}
              stroke="var(--color-text-muted)"
              strokeDasharray="4 4"
            />
            {/*
              Recharts animates bars up from zero on every mount. In a data-first
              design that is noise, it delays the figures being readable, and CSS
              `prefers-reduced-motion` cannot switch it off because the animation
              is driven in JavaScript.
            */}
            <Bar dataKey="energy_kcal" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {days.map((day) => (
                <Cell
                  key={day.date}
                  fill={
                    day.energy_kcal > day.target_kcal
                      ? 'var(--color-over)'
                      : 'var(--color-on-target)'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* The chart's data, for screen readers and for anyone who wants the figures. */}
      <table className="sr-only">
        <caption>Energy each day against target</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Energy</th>
            <th scope="col">Target</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{day.weekday}</th>
              <td>{formatAmount(day.energy_kcal, 'kcal')} kcal</td>
              <td>{formatAmount(day.target_kcal, 'kcal')} kcal</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
