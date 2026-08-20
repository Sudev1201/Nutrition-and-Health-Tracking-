import { cx } from '../lib/cx'
import { formatAmount, formatPercent, unitLabel } from '../lib/format'
import type { NutrientUnit } from '../lib/format'
import { nutrientStatus } from '../lib/status'
import type { NutrientKind } from '../lib/status'
import { STATUS_FILL, STATUS_LABELS, STATUS_TEXT } from './statusPresentation'

/** A headline figure — energy and the macros at the top of Today. */
export function StatTile({
  label,
  consumed,
  target,
  unit,
  ear = null,
  tul = null,
  kind = 'target',
}: {
  label: string
  consumed: number
  target: number
  unit: NutrientUnit
  ear?: number | null
  tul?: number | null
  kind?: NutrientKind
}) {
  const status = nutrientStatus({ consumed, ear, rda: target, tul, kind })
  const percent = formatPercent(consumed, target)

  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <p className="text-xs text-text-muted">{label}</p>

      {/*
        Value and target are stacked rather than inline. Two tiles fit across a
        390px phone, which leaves about 165px each -- not enough for
        "1,420 / 2,110 kcal" on one line, and it wrapped the unit onto its own
        row, leaving the tiles ragged and different heights.
      */}
      <p className="mt-0.5 text-2xl leading-tight font-semibold">
        {formatAmount(consumed, unit)}
      </p>
      <p className="text-xs text-text-muted">
        of {formatAmount(target, unit)} {unitLabel(unit)}
      </p>

      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
        <div
          className={cx('h-full', STATUS_FILL[status])}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>

      <p className={cx('mt-1 text-xs', STATUS_TEXT[status])}>
        {percent}% · {STATUS_LABELS[status]}
      </p>
    </div>
  )
}
