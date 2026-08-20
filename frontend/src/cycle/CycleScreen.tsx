import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import { Badge } from '../ui/Badge'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { DemoDataBanner, Skeleton } from '../ui/feedback'
import type { CycleState, EvidenceGrade } from './types'

const EVIDENCE_LABELS: Record<EvidenceGrade, string> = {
  strong: 'Strong evidence',
  moderate: 'Moderate evidence',
  low: 'Low-quality evidence',
  // Never presented as established nutrition.
  traditional: 'Traditional practice, not established nutrition',
}

function useCycle() {
  return useQuery({
    queryKey: ['cycle'],
    queryFn: () => api.get<CycleState>('/cycle'),
    retry: false,
  })
}

function useSetCycleEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => api.patch('/cycle', { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cycle'] }),
  })
}

export function CycleScreen() {
  const cycle = useCycle()
  const setEnabled = useSetCycleEnabled()

  if (cycle.isPending) return <Skeleton className="h-64 w-full" />
  if (cycle.isError || cycle.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Cycle tracking could not be loaded. Please try again.
      </p>
    )
  }

  const data = cycle.data

  return (
    <section className="space-y-4">
      <DemoDataBanner endpoint="GET /cycle" />

      <Card>
        <Toggle
          label="Track my cycle"
          description="Off by default, and private within a household unless you choose to share it."
          checked={data.enabled}
          onChange={(checked) => setEnabled.mutate(checked)}
        />
      </Card>

      {data.enabled && (
        <>
          {data.referral !== null && (
            <div
              role="alert"
              className="flex gap-2 rounded-card border border-above-limit/40 bg-above-limit/5 p-3 text-sm text-above-limit"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>
                <strong className="font-medium">Please see a clinician.</strong>{' '}
                {data.referral.reason} Heavy bleeding needs medical assessment — around one in
                five people with it has an underlying bleeding disorder. This is not something
                to address with food.
              </span>
            </div>
          )}

          {/*
            These two statements are load-bearing, not reassurance. Both features
            are the intuitive design and both are wrong, so the app says out loud
            what it does NOT do.
          */}
          <Card>
            <CardTitle>What this does and doesn’t change</CardTitle>
            <ul className="mt-2 space-y-2 text-sm text-text-muted">
              <li>
                Your <strong className="text-text">iron target does not change</strong> when you
                log a period. The ICMR figure for women already averages menstrual loss across
                the whole cycle, so raising it would count the same loss twice — and your body
                already absorbs more iron during menses.
              </li>
              <li>
                Your <strong className="text-text">calorie target does not change</strong> with
                cycle phase. The real luteal increase is around 32 kcal a day once anovulatory
                cycles are accounted for, which is far inside normal day-to-day variation.
              </li>
              <li>
                What does change is coaching: when to take coffee or tea, and what to pair an
                iron-rich meal with.
              </li>
            </ul>
          </Card>

          <Card>
            <CardTitle>Around your period</CardTitle>
            <ul className="mt-2 space-y-4">
              {data.coaching.map((note) => (
                <li key={note.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{note.title}</p>
                    <Badge tone={note.evidence === 'strong' ? 'accent' : 'neutral'}>
                      {EVIDENCE_LABELS[note.evidence]}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-sm text-text-muted">{note.body}</p>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </section>
  )
}
