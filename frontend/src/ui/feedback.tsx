import type { ReactNode } from 'react'
import { cx } from '../lib/cx'

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-card border border-dashed border-border p-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      {description !== undefined && (
        <p className="mx-auto mt-1 max-w-prose text-sm text-text-muted">{description}</p>
      )}
      {action !== undefined && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cx('animate-pulse rounded bg-border', className)}
    />
  )
}

/**
 * Marks a screen whose numbers come from fixtures rather than from the nutrition
 * engine. This is a health app: a plausible-looking calcium target that was typed
 * by hand must never be mistaken for one computed from ICMR-NIN figures. Removed
 * per screen as its endpoint lands.
 */
export function DemoDataBanner({ endpoint }: { endpoint: string }) {
  return (
    <div
      role="note"
      className="mb-4 rounded-card border border-carried/40 bg-carried/10 px-3 py-2 text-xs text-carried"
    >
      <strong className="font-medium">Demo data.</strong> These numbers are fixtures,
      not computed from your profile — <code>{endpoint}</code> is not built yet.
    </div>
  )
}
