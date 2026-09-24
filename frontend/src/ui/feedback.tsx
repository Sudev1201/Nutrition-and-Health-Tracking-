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
