import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { formatDay } from '../lib/format'
import { todayIso } from '../today/useToday'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import { CycleDayForm } from './CycleDayForm'
import { ScreeningCard } from './ScreeningCard'
import { FLOW_LABELS, SYMPTOM_LABELS } from './types'
import type { CycleDay, CycleState, EvidenceGrade, IneligibleReason } from './types'
import { useClearCycleDay, useCycle, useEraseCycle, useSetCycleEnabled } from './useCycle'

const EVIDENCE_LABELS: Record<EvidenceGrade, string> = {
  strong: 'Strong evidence',
  moderate: 'Moderate evidence',
  low: 'Low-quality evidence',
  // Never presented as established nutrition.
  traditional: 'Traditional practice, not established nutrition',
}

const PROFILE_LINK =
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface'

function NotOffered({ reason }: { reason: IneligibleReason | null }) {
  const action = (
    <Link to="/profile/about" className={PROFILE_LINK}>
      Review your profile
    </Link>
  )
  if (reason === 'postmenopausal') {
    return (
      <EmptyState
        title="Cycle tracking is for women who have periods"
        description="Your profile says you no longer have periods, so your iron target uses the IOM figure for women after menopause. Any bleeding after menopause should be checked by a clinician."
        action={action}
      />
    )
  }
  return (
    <EmptyState
      title="Cycle tracking is for profiles set to female"
      description="The sex on your profile chooses which ICMR reference values apply, so change it only if it is wrong."
      action={action}
    />
  )
}

function describeDay(day: CycleDay): string {
  const bleeding = day.flow === null ? 'no bleeding' : `${FLOW_LABELS[day.flow].toLowerCase()} flow`
  return [bleeding, ...day.symptoms.map((symptom) => SYMPTOM_LABELS[symptom].toLowerCase())].join(
    ', ',
  )
}

function RecentDays({ data }: { data: CycleState }) {
  const clear = useClearCycleDay()

  return (
    <Card>
      <CardTitle>Recent days</CardTitle>
      {data.last_period_start !== null && (
        <p className="mt-1 text-sm text-text-muted">
          Your last period started on {formatDay(data.last_period_start)}.
        </p>
      )}
      {data.days.length === 0 ? (
        <p className="mt-2 text-sm text-text-muted">Nothing logged in the last 90 days.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {data.days.map((day) => (
            <li key={day.date} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>
                <span className="font-medium">{formatDay(day.date)}</span> — {describeDay(day)}
              </span>
              <Button
                variant="quiet"
                aria-label={`Remove ${formatDay(day.date)}`}
                disabled={clear.isPending}
                onClick={() => clear.mutate(day.date)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function EraseHistory() {
  const erase = useEraseCycle()
  const [confirming, setConfirming] = useState(false)

  return (
    <Card>
      <CardTitle>Your cycle history</CardTitle>
      <p className="mt-1 text-sm text-text-muted">
        Private to you, even in a household, unless you choose to share your health details.
      </p>
      {confirming ? (
        <div className="mt-3 space-y-2">
          <p className="text-sm">
            This deletes every day, symptom and answer you have logged, and turns tracking off.
            It cannot be undone.
          </p>
          <div className="flex gap-2">
            <Button
              variant="danger"
              disabled={erase.isPending}
              onClick={() => erase.mutate(undefined, { onSuccess: () => setConfirming(false) })}
            >
              Delete everything
            </Button>
            <Button onClick={() => setConfirming(false)}>Keep it</Button>
          </div>
        </div>
      ) : (
        <Button variant="danger" className="mt-3" onClick={() => setConfirming(true)}>
          Delete my cycle history
        </Button>
      )}
    </Card>
  )
}

export function CycleScreen() {
  const cycle = useCycle(todayIso())
  const setEnabled = useSetCycleEnabled()

  if (cycle.isPending) return <Skeleton className="h-64 w-full" />
  if (cycle.error instanceof ApiError && cycle.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your profile"
        description="Whether cycle tracking applies depends on your profile, so there is nothing to show until you have told us about yourself."
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }
  if (cycle.isError || cycle.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Cycle tracking could not be loaded. Please try again.
      </p>
    )
  }

  const data = cycle.data
  if (!data.eligible) {
    // Data logged before a profile change is hidden, but must stay erasable.
    return (
      <section className="space-y-4">
        <NotOffered reason={data.ineligible_reason} />
        {data.has_history && <EraseHistory />}
      </section>
    )
  }

  return (
    <section className="space-y-4">
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
                five adolescents with it has an underlying bleeding disorder. This is not
                something to address with food.
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
                iron-rich meal with. It follows the days and symptoms you log, never a predicted
                calendar.
              </li>
            </ul>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <CycleDayForm />
            {/* Keyed on the saved answers, so the boxes reset when they change. */}
            <ScreeningCard
              key={data.screening?.answered_on ?? 'none'}
              saved={data.screening}
            />
          </div>

          <RecentDays data={data} />

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

          <EraseHistory />
        </>
      )}
      {!data.enabled && data.has_history && <EraseHistory />}
    </section>
  )
}
