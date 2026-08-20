import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatAmount } from '../lib/format'
import { Card, CardTitle } from '../ui/Card'

/** `GET /profile/baseline` — what a usual day adds up to, against the target. */
interface Baseline {
  has_usual_intake: boolean
  usual_energy_kcal: number | null
  target_energy_kcal: number
  difference_kcal: number | null
  implausible: boolean
  note: string | null
}

function useBaseline(date: string) {
  return useQuery({
    queryKey: ['profile', 'baseline', date],
    queryFn: () => api.get<Baseline>(`/profile/baseline?date=${date}`),
    retry: false,
  })
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

      {data.note !== null && (
        <p className="mt-2 flex gap-2 rounded-card border border-over/40 bg-over/5 p-2 text-xs text-over">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{data.note}</span>
        </p>
      )}
    </Card>
  )
}
