import { formatAmount, formatPercent, formatWithUnit, unitLabel } from '../lib/format'
import type { NutrientUnit } from '../lib/format'
import { nutrientStatus } from '../lib/status'
import type { NutrientKind } from '../lib/status'
import { STATUS_FILL, STATUS_LABELS, STATUS_TEXT } from './statusPresentation'

export interface NutrientBarProps {
  name: string
  unit: NutrientUnit
  consumed: number
  /** Today's effective target — the RDA after the compensation ledger is applied. */
  target: number
  /** EAR adequacy floor; a shortfall is only "real" below this. */
  ear: number | null
  /** Tolerable Upper Limit, or null where ICMR set none. */
  tul: number | null
  kind: NutrientKind
  /** What the ledger added to today's target. */
  carriedIn?: number
  /** The weekday that carry came from, e.g. "Friday". */
  carriedFrom?: string
}

export function NutrientBar({
  name,
  unit,
  consumed,
  target,
  ear,
  tul,
  kind,
  carriedIn,
  carriedFrom,
}: NutrientBarProps) {
  // Status is judged against today's effective target, because that is what the
  // app is actually asking of you -- but against the real TUL, never an adjusted
  // one, since the spec forbids an adjusted target from exceeding the limit.
  const status = nutrientStatus({ consumed, ear, rda: target, tul, kind })

  // The track has to stretch to fit an overshoot, or a 260% day would render
  // identically to a 100% one.
  const scaleMax = Math.max(target, consumed)
  const percentOf = (value: number) => `${(value / scaleMax) * 100}%`

  const showTargetTick = consumed > target
  const showLimitTick = tul !== null && tul <= scaleMax

  const amounts = `${formatAmount(consumed, unit)} / ${formatWithUnit(target, unit)}`

  return (
    <div className="py-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{name}</span>
        <span className="text-sm text-text-muted">{amounts}</span>
      </div>

      <div className="mt-1.5 flex items-center gap-2">
        <div
          role="progressbar"
          aria-label={name}
          aria-valuenow={consumed}
          aria-valuemin={0}
          aria-valuemax={scaleMax}
          className="relative h-2 flex-1 overflow-hidden rounded-full bg-border"
        >
          {/*
            The carried segment is drawn first and sits under the consumed fill, so
            the ledger's contribution to the target is visible as its own colour
            rather than being implied by a number in the caption alone.
          */}
          {carriedIn !== undefined && carriedIn > 0 && (
            <div
              className="absolute inset-y-0 right-0 bg-carried/30"
              style={{ width: percentOf(carriedIn) }}
            />
          )}

          <div
            className={`absolute inset-y-0 left-0 ${STATUS_FILL[status]}`}
            style={{ width: percentOf(consumed) }}
          />

          {showTargetTick && (
            <span
              title={`Target ${formatWithUnit(target, unit)}`}
              className="absolute inset-y-0 w-0.5 bg-text"
              style={{ left: percentOf(target) }}
            />
          )}

          {showLimitTick && tul !== null && (
            <span
              title={`Upper limit ${formatWithUnit(tul, unit)}`}
              className="absolute inset-y-0 w-0.5 bg-above-limit"
              style={{ left: percentOf(tul) }}
            />
          )}
        </div>

        <span className="w-10 shrink-0 text-right text-sm text-text-muted">
          {formatPercent(consumed, target)}%
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 text-xs">
        <span className={STATUS_TEXT[status]}>{STATUS_LABELS[status]}</span>
        {carriedIn !== undefined && carriedIn > 0 && carriedFrom !== undefined && (
          <span className="text-carried">
            {`+${formatAmount(carriedIn, unit)} ${unitLabel(unit)} carried from ${carriedFrom}`}
          </span>
        )}
      </div>
    </div>
  )
}
