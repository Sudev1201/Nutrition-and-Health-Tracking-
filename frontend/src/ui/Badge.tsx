import type { ReactNode } from 'react'
import { cx } from '../lib/cx'

type Tone = 'neutral' | 'accent' | 'estimated' | 'warning'

const TONES: Record<Tone, string> = {
  neutral: 'border-border text-text-muted',
  accent: 'border-accent/40 text-accent bg-accent-soft',
  // Restaurant and eyeballed portions. The weekly report separates these from
  // measured intake, so they must be visually distinct wherever they appear.
  estimated: 'border-over/40 text-over',
  warning: 'border-above-limit/40 text-above-limit',
}

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: Tone
  children: ReactNode
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs',
        TONES[tone],
      )}
    >
      {children}
    </span>
  )
}
