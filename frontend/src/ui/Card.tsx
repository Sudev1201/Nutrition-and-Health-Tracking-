import type { ReactNode } from 'react'
import { cx } from '../lib/cx'

export function Card({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cx(
        'rounded-card border border-border bg-surface p-4',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-medium text-text-muted">{children}</h3>
}
