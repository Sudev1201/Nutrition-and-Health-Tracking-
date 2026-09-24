import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatAmount } from '../lib/format'
import type { DayState, ReportDay } from './types'

/** What a day without a reading says in place of a figure. */
const NO_READING: Record<Exclude<DayState, 'tracked'>, string> = {
  untracked: 'Nothing logged',
  'in-progress': 'Today, not over yet',
  future: 'Still to come',
}

function energyWords(day: ReportDay): string {
  return day.state === 'tracked'
    ? `${formatAmount(day.energy_kcal, 'kcal')} kcal`
    : NO_READING[day.state]
}

/**
 * A logged day is a solid bar in the status colour Today uses. A day without a
 * reading is an outline drawn to its target. A zero-height bar would draw it as a
 * day of eating nothing, which the diary cannot say. Dashed means nothing was
 * logged. Dotted and faint means the day is not over yet.
 */
function barStyle(day: ReportDay) {
  if (day.state === 'tracked') {
    return {
      fill: day.energy_kcal > day.target_kcal ? 'var(--color-over)' : 'var(--color-on-target)',
    }
  }
  const untracked = day.state === 'untracked'
  return {
    fill: 'transparent',
    stroke: 'var(--color-text-muted)',
    strokeWidth: 1.5,
    strokeDasharray: untracked ? '4 3' : '1 3',
    strokeOpacity: untracked ? 1 : 0.6,
  }
}

/**
 * Energy for each day against that day's own target.
 *
 * The target is a line through the week rather than one reference line.
 * - A recalibration moves it from the day it took effect, so an earlier day is
 *   never judged against a figure it did not have.
 * - Each figure is the day's base target, before any carry, which is what the
 *   backend reports.
 *
 * The chart is decorative for assistive technology (`aria-hidden`). The same
 * figures are published as a real table beside it, because Recharts emits SVG
 * with no text alternative.
 */
export function EnergyChart({ days }: { days: ReportDay[] }) {
  const data = days.map((day) => ({
    ...day,
    bar_kcal: day.state === 'tracked' ? day.energy_kcal : day.target_kcal,
  }))

  return (
    <>
      <div aria-hidden="true">
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
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
                formatter={(value, name, item) =>
                  name === 'Target'
                    ? [`${formatAmount(Number(value ?? 0), 'kcal')} kcal`, name]
                    : [energyWords(item.payload as ReportDay), name]
                }
              />
              {/*
                Recharts animates bars up from zero on every mount. In a data-first
                design that is noise, it delays the figures being readable, and CSS
                `prefers-reduced-motion` cannot switch it off because the animation
                is driven in JavaScript.
              */}
              <Bar name="Energy" dataKey="bar_kcal" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {days.map((day) => (
                  <Cell key={day.date} {...barStyle(day)} />
                ))}
              </Bar>
              <Line
                name="Target"
                dataKey="target_kcal"
                type="step"
                stroke="var(--color-text-muted)"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-text-muted">
          The dashed line is each day’s own target. An outlined bar is a day with nothing
          logged, or one not over yet.
        </p>
      </div>

      {/* The chart's data, for screen readers and for anyone who wants the figures. */}
      <table className="sr-only">
        <caption>Energy each day against that day’s target</caption>
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
              <td>{energyWords(day)}</td>
              <td>{formatAmount(day.target_kcal, 'kcal')} kcal</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
