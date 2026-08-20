import { useId } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { cx } from '../lib/cx'

const CONTROL =
  'w-full rounded-control border border-border bg-surface px-3 py-2 text-text placeholder:text-text-muted disabled:opacity-50'

/** Labels a control and, when given, ties an error message to it for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: (props: { id: string; 'aria-describedby': string | undefined }) => ReactNode
}) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = cx(hint !== undefined && hintId, error !== undefined && errorId)

  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {hint !== undefined && (
        <p id={hintId} className="mb-1 text-xs text-text-muted">
          {hint}
        </p>
      )}
      {children({ id, 'aria-describedby': describedBy === '' ? undefined : describedBy })}
      {error !== undefined && (
        <p id={errorId} role="alert" className="mt-1 text-xs text-above-limit">
          {error}
        </p>
      )}
    </div>
  )
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input type="text" className={cx(CONTROL, className)} {...rest} />
}

/**
 * Grams, weights and lab values. `inputMode="decimal"` raises the numeric keypad
 * on a phone; `type="text"` rather than `type="number"` avoids the scroll-wheel
 * increment and the silently-dropped invalid value that `number` inputs have.
 */
export function NumberInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="text"
      inputMode="decimal"
      autoComplete="off"
      className={cx(CONTROL, className)}
      {...rest}
    />
  )
}

export function Select({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(CONTROL, className)} {...rest}>
      {children}
    </select>
  )
}

export function Checkbox({
  label,
  ...rest
}: { label: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex min-h-11 items-center gap-3 text-sm">
      <input
        type="checkbox"
        className="size-4 shrink-0 accent-[var(--color-accent)]"
        {...rest}
      />
      <span>{label}</span>
    </label>
  )
}

/** A switch for settings that take effect immediately, such as a slot's reminder. */
export function Toggle({
  label,
  checked,
  onChange,
  description,
}: {
  label: ReactNode
  checked: boolean
  onChange: (checked: boolean) => void
  description?: string
}) {
  return (
    <label className="flex min-h-11 items-center justify-between gap-4 py-2 text-sm">
      <span>
        <span className="block">{label}</span>
        {description !== undefined && (
          <span className="block text-xs text-text-muted">{description}</span>
        )}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-5 shrink-0 accent-[var(--color-accent)]"
      />
    </label>
  )
}
