import { cx } from '../lib/cx'

export interface SegmentedOption<T extends string> {
  value: T
  /** What is shown. May be abbreviated to fit a narrow control. */
  label: string
  /**
   * The full name, when `label` is abbreviated for space. A tab announced as
   * "Sun" is worse than useless to a screen-reader user; the short form is a
   * layout compromise and should not leak into the accessible name.
   */
  a11yLabel?: string
}

/**
 * A radio group styled as a segmented control. Real radio inputs rather than
 * buttons, so arrow-key navigation and the checked state come from the platform.
 */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: readonly SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-control border border-border bg-surface p-0.5"
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <label
            key={option.value}
            className={cx(
              'flex min-h-9 cursor-pointer items-center rounded-[4px] px-3 text-sm',
              selected ? 'bg-accent text-surface' : 'text-text-muted',
            )}
          >
            <input
              type="radio"
              className="sr-only"
              name={label}
              value={option.value}
              aria-label={option.a11yLabel}
              checked={selected}
              onChange={() => onChange(option.value)}
            />
            {option.label}
          </label>
        )
      })}
    </div>
  )
}
