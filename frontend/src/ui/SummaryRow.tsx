import type { ReactNode } from 'react'

/**
 * One label-and-value line in a read-only summary.
 *
 * A `<dl>` rather than a table or a stack of divs: these genuinely are term and
 * description pairs, and the markup is what lets a screen reader announce
 * "Activity level, Moderate" instead of two unrelated strings.
 */
export function SummaryList({ children }: { children: ReactNode }) {
  return <dl className="divide-y divide-border">{children}</dl>
}

export function SummaryRow({
  label,
  children,
  hint,
}: {
  label: string
  children: ReactNode
  hint?: string
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2">
      <dt className="text-sm text-text-muted">{label}</dt>
      <dd className="min-w-0 text-right text-sm">
        {children}
        {hint !== undefined && <span className="block text-xs text-text-muted">{hint}</span>}
      </dd>
    </div>
  )
}

/** For an answer the user has not given. Says so, rather than showing a blank. */
export function NotSet({ children = 'Not set' }: { children?: ReactNode }) {
  return <span className="text-text-muted">{children}</span>
}
