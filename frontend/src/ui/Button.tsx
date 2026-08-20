import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cx } from '../lib/cx'

type Variant = 'primary' | 'secondary' | 'quiet' | 'danger'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-surface border-accent',
  secondary: 'bg-surface text-text border-border hover:bg-surface-alt',
  quiet: 'bg-transparent text-text-muted border-transparent hover:bg-surface-alt',
  danger: 'bg-surface text-above-limit border-above-limit/40 hover:bg-above-limit/10',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  /** Stretch to the container — the default on a phone, where buttons are full width. */
  block?: boolean
  children: ReactNode
}

export function Button({
  variant = 'secondary',
  block = false,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // Buttons default to type="submit" inside a form, which silently submits
      // the wizard when someone hits "Add another medication".
      type={type}
      className={cx(
        // 44px minimum height: below that, thumb accuracy on a phone falls off sharply.
        'inline-flex min-h-11 items-center justify-center gap-2 rounded-control border px-4 text-sm font-medium',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        block && 'w-full',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
