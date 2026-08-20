import { useEffect, useId, useState } from 'react'
import { Search } from 'lucide-react'

const DEBOUNCE_MS = 300

/**
 * A debounced search box.
 *
 * The debounce is not cosmetic: `GET /foods/search` runs two ILIKE queries per
 * call, and firing per keystroke would send six overlapping requests for "pongal"
 * whose responses can arrive out of order. Blank terms are withheld entirely —
 * the endpoint answers those with a 422 by design, because a stray space used to
 * match every dish in the database.
 */
export function SearchField({
  label,
  placeholder,
  onSearch,
}: {
  label: string
  placeholder?: string
  onSearch: (term: string) => void
}) {
  const id = useId()
  const [term, setTerm] = useState('')

  useEffect(() => {
    const trimmed = term.trim()
    if (trimmed === '') return

    const timer = setTimeout(() => onSearch(trimmed), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [term, onSearch])

  return (
    <div className="relative">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-muted"
      />
      <input
        id={id}
        type="search"
        aria-label={label}
        placeholder={placeholder}
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        className="w-full rounded-control border border-border bg-surface py-2 pr-3 pl-9 placeholder:text-text-muted"
      />
    </div>
  )
}
