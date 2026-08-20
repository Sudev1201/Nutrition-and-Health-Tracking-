import { useCallback, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { FULL_MATCH_LIMIT, useFoodSearch } from '../foods/useFoodSearch'
import { Badge } from './Badge'
import { SearchField } from './SearchField'

export interface FoodRef {
  label: string
  /**
   * Null only for rows saved before the list was restricted to the database.
   * Anything added now comes from search and carries an id.
   */
  food_id: string | null
  food_kind: 'dish' | 'ingredient' | null
}

/**
 * Build a list of foods, as many as the user wants.
 *
 * Items come from the food database only. Each one therefore carries an id the
 * planner can act on, rather than a name it would have to string-match against
 * 547 ingredients — and a typed name could never be costed against the nutrient
 * tables at all.
 *
 * Every match is offered rather than a truncated handful: "chicken" alone spans
 * 44 rows across dishes and ingredients, and showing six of them made the
 * database look far smaller than it is.
 */
export function FoodListField({
  label,
  hint,
  items,
  onChange,
  searchLabel,
}: {
  label: string
  hint: string
  items: FoodRef[]
  onChange: (items: FoodRef[]) => void
  searchLabel: string
}) {
  const [term, setTerm] = useState('')
  const { data: results, isFetching } = useFoodSearch(term, FULL_MATCH_LIMIT)
  const handleSearch = useCallback((value: string) => setTerm(value), [])

  function add(item: FoodRef) {
    // Adding the same food twice is a no-op rather than a duplicate row.
    const already = items.some((existing) => existing.food_id === item.food_id)
    if (!already) onChange([...items, item])
    setTerm('')
  }

  function remove(index: number) {
    onChange(items.filter((_, position) => position !== index))
  }

  return (
    <fieldset className="mb-4">
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      <p className="mb-2 text-xs text-text-muted">{hint}</p>

      {items.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2">
          {items.map((item, index) => (
            <li key={`${item.label}-${index}`}>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-alt py-1 pr-1 pl-3 text-sm">
                {item.label}
                {item.food_id === null && (
                  <span className="text-xs text-text-muted">(typed)</span>
                )}
                <button
                  type="button"
                  aria-label={`Remove ${item.label}`}
                  onClick={() => remove(index)}
                  className="flex size-6 items-center justify-center rounded-full text-text-muted hover:bg-border"
                >
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <SearchField label={searchLabel} placeholder="Search foods…" onSearch={handleSearch} />

      {term !== '' && (
        <div className="mt-2 overflow-hidden rounded-card border border-border">
          {isFetching && <p className="p-3 text-sm text-text-muted">Searching…</p>}

          {!isFetching && results !== undefined && results.length > 0 && (
            // Scrolls rather than truncates, so a broad term stays usable on a
            // phone without hiding matches.
            <ul className="max-h-72 divide-y divide-border overflow-y-auto">
              {results.map((result) => (
                <li key={`${result.kind}-${result.id}`}>
                  <button
                    type="button"
                    // Named "Add X" rather than just "X", so it is distinct from
                    // the "Remove X" chip for the same food.
                    aria-label={`Add ${result.name}`}
                    onClick={() =>
                      add({ label: result.name, food_id: result.id, food_kind: result.kind })
                    }
                    className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-sm hover:bg-surface-alt"
                  >
                    <Plus className="size-4 shrink-0 text-accent" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{result.name}</span>
                    <Badge>{result.source}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/*
            No free-text fallback. An entry with no food behind it cannot be
            costed and the planner could only string-match it, so the list stays
            the database's rather than the user's typing.
          */}
          {!isFetching && results !== undefined && results.length === 0 && (
            <p className="p-3 text-sm text-text-muted">
              Nothing in the food database matches “{term}”. Try a simpler or more general
              name — the individual ingredients usually work.
            </p>
          )}

          {!isFetching && results !== undefined && results.length >= FULL_MATCH_LIMIT && (
            <p className="border-t border-border p-2 text-xs text-text-muted">
              Showing the first {FULL_MATCH_LIMIT} matches — type more to narrow it down.
            </p>
          )}
        </div>
      )}
    </fieldset>
  )
}
