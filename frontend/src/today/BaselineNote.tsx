import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatAmount, unitLabel } from '../lib/format'
import type { NutrientUnit } from '../lib/format'
import { Card, CardTitle } from '../ui/Card'

/** One nutrient's usual-day figure against its published RDA. */
interface NutrientBaseline {
  code: string
  display_name: string
  unit: NutrientUnit
  category: string
  kind: 'target' | 'ceiling'
  ear: number | null
  rda: number
  tul: number | null
  usual: number
  /**
   * Whether a usual day misses the mark, in whichever direction is wrong for
   * this nutrient. The backend decides it, because that is where the
   * target-versus-ceiling meaning of `kind` lives.
   */
  off_target: boolean
}

/** `GET /profile/baseline` — what a usual day adds up to, against the target. */
interface Baseline {
  has_usual_intake: boolean
  usual_energy_kcal: number | null
  target_energy_kcal: number
  difference_kcal: number | null
  implausible: boolean
  note: string | null
  nutrients: NutrientBaseline[]
}

function useBaseline(date: string) {
  return useQuery({
    queryKey: ['profile', 'baseline', date],
    queryFn: () => api.get<Baseline>(`/profile/baseline?date=${date}`),
    retry: false,
  })
}

/**
 * The nutrients a usual day gets wrong, in either direction.
 *
 * Energy is excluded because the sentence above already covers it in prose, and
 * repeating it here reads as two different findings about the same number.
 */
function NutrientGaps({ nutrients }: { nutrients: NutrientBaseline[] }) {
  const gaps = nutrients.filter((item) => item.off_target && item.code !== 'energy')

  if (gaps.length === 0) return null

  return (
    <div className="mt-3 border-t border-border pt-3">
      <p className="text-xs font-medium text-text-muted">How a usual day compares</p>
      <ul className="mt-1.5 space-y-1">
        {gaps.map((item) => (
          <li key={item.code} className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 flex-1 truncate">{item.display_name}</span>
            <span className="shrink-0 text-text-muted">
              {formatAmount(item.usual, item.unit)} / {formatAmount(item.rda, item.unit)}{' '}
              {unitLabel(item.unit)}
            </span>
            {/*
              A ceiling nutrient over its figure is too much, not too little.
              Labelling both "short" would tell someone eating a lot of salt to
              eat more of it.
            */}
            <span className="w-16 shrink-0 text-right text-xs text-text-muted">
              {item.kind === 'ceiling' ? 'too much' : 'too little'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The gap between what the user eats now and what they need.
 *
 * Not a target — the target still comes from the ICMR energy formula. This exists
 * because a first-week plan that ignores where someone is starting from asks for
 * a jump rather than a step.
 */
export function BaselineNote({ date }: { date: string }) {
  const baseline = useBaseline(date)

  if (baseline.isPending || baseline.isError || baseline.data === undefined) return null

  const data = baseline.data

  if (!data.has_usual_intake || data.usual_energy_kcal === null) {
    return (
      <Card className="mb-4">
        <CardTitle>Where you are starting from</CardTitle>
        <p className="mt-1 text-sm text-text-muted">
          You have not described a usual day yet, so the app cannot tell how far today’s target
          is from what you normally eat.{' '}
          <Link to="/profile" className="text-accent underline">
            Add a usual day
          </Link>{' '}
          and it will work the difference out.
        </p>
      </Card>
    )
  }

  const difference = data.difference_kcal ?? 0
  const below = difference < 0

  return (
    <Card className="mb-4">
      <CardTitle>Where you are starting from</CardTitle>
      <p className="mt-1 text-sm">
        A usual day for you is about{' '}
        <strong className="font-semibold">
          {formatAmount(data.usual_energy_kcal, 'kcal')} kcal
        </strong>
        , against a target of {formatAmount(data.target_energy_kcal, 'kcal')} kcal — about{' '}
        <strong className="font-semibold">
          {formatAmount(Math.abs(difference), 'kcal')} kcal {below ? 'below' : 'above'}
        </strong>
        .
      </p>

      <NutrientGaps nutrients={data.nutrients ?? []} />

      {data.note !== null && (
        <p className="mt-2 flex gap-2 rounded-card border border-over/40 bg-over/5 p-2 text-xs text-over">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{data.note}</span>
        </p>
      )}
    </Card>
  )
}
