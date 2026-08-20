import { useCallback, useState } from 'react'
import { Badge } from '../ui/Badge'
import { EmptyState, Skeleton } from '../ui/feedback'
import { SearchField } from '../ui/SearchField'
import { useFoodSearch } from './useFoodSearch'
import type { FoodResult } from './useFoodSearch'

export function FoodResultRow({
  result,
  onSelect,
}: {
  result: FoodResult
  onSelect?: (result: FoodResult) => void
}) {
  const content = (
    <>
      <span className="min-w-0 flex-1 truncate text-sm">{result.name}</span>
      <Badge tone={result.kind === 'dish' ? 'accent' : 'neutral'}>
        {result.kind === 'dish' ? 'Dish' : 'Ingredient'}
      </Badge>
      <Badge>{result.source}</Badge>
    </>
  )

  if (onSelect === undefined) {
    return <li className="flex min-h-14 items-center gap-2 px-3">{content}</li>
  }

  return (
    <li>
      <button
        type="button"
        // "Add X" rather than bare "X", so it is distinct from any chip or
        // diary row naming the same food.
        aria-label={`Add ${result.name}`}
        onClick={() => onSelect(result)}
        className="flex min-h-14 w-full items-center gap-2 px-3 text-left hover:bg-surface-alt"
      >
        {content}
      </button>
    </li>
  )
}

/**
 * Search across dishes and ingredients. This is the only reachable view of the
 * food database, and it doubles as the search step of the logging flow — which is
 * why the row is exported separately and takes an optional select handler.
 */
export function FoodSearchScreen({
  onSelect,
}: {
  onSelect?: (result: FoodResult) => void
}) {
  const [term, setTerm] = useState('')
  const { data, isFetching, isError } = useFoodSearch(term)

  // Stable identity, or SearchField's debounce effect re-runs on every render and
  // the timer never gets the chance to fire.
  const handleSearch = useCallback((value: string) => setTerm(value), [])

  return (
    <section>
      <SearchField
        label="Search foods"
        placeholder="idli, sambar, rice…"
        onSearch={handleSearch}
      />

      {isError && (
        <p role="alert" className="mt-4 text-sm text-above-limit">
          That could not be searched just now. Please try again.
        </p>
      )}

      {isFetching && <Skeleton className="mt-4 h-14 w-full" />}

      {!isFetching && !isError && data !== undefined && data.length === 0 && (
        <div className="mt-4">
          <EmptyState
            title="Nothing matched that"
            description="Try a shorter word, or the English name — the database is English-only, though regional names like keerai are searchable as aliases."
          />
        </div>
      )}

      {!isError && data !== undefined && data.length > 0 && (
        <ul className="mt-4 divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
          {data.map((result) => (
            <FoodResultRow key={`${result.kind}-${result.id}`} result={result} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </section>
  )
}
