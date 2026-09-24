import { useState } from 'react'
import { formatDay } from '../lib/format'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox } from '../ui/fields'
import type { Screening, ScreeningAnswers } from './types'
import { useSaveScreening } from './useCycle'

/*
 * The validated heavy-bleeding questions. A yes to any of them produces a
 * clinician referral — never a nutrient change. Flow logged as "heavy" is not
 * one of them: a self-rating is not a screening question.
 */
const QUESTIONS: { field: keyof ScreeningAnswers; label: string }[] = [
  {
    field: 'soaks_within_two_hours',
    label: 'Do you soak through a pad or tampon in two hours or less?',
  },
  { field: 'longer_than_seven_days', label: 'Does your period usually last more than seven days?' },
  { field: 'large_clots', label: 'Do you pass clots larger than a ₹10 coin (about 2.5 cm)?' },
  {
    field: 'flooding',
    label: 'Do you have flooding — bleeding through to your clothes or bedding?',
  },
]

function answersOf(saved: Screening | null): ScreeningAnswers {
  return {
    soaks_within_two_hours: saved?.soaks_within_two_hours ?? false,
    longer_than_seven_days: saved?.longer_than_seven_days ?? false,
    large_clots: saved?.large_clots ?? false,
    flooding: saved?.flooding ?? false,
  }
}

export function ScreeningCard({ saved }: { saved: Screening | null }) {
  const save = useSaveScreening()
  const [answers, setAnswers] = useState(() => answersOf(saved))

  return (
    <Card>
      <CardTitle>Heavy bleeding check</CardTitle>
      <p className="mt-1 text-sm text-text-muted">
        Four questions clinicians use to spot bleeding that needs looking into. A yes to any of
        them means seeing a clinician. It never changes a nutrient target.
      </p>
      <div className="mt-2">
        {QUESTIONS.map(({ field, label }) => (
          <Checkbox
            key={field}
            label={label}
            checked={answers[field]}
            onChange={(event) =>
              setAnswers((current) => ({ ...current, [field]: event.target.checked }))
            }
          />
        ))}
      </div>
      {saved !== null && (
        <p className="text-xs text-text-muted">Last answered {formatDay(saved.answered_on)}.</p>
      )}
      <Button
        className="mt-3"
        disabled={save.isPending}
        onClick={() => save.mutate(answers)}
      >
        Save answers
      </Button>
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          Your answers could not be saved. Please try again.
        </p>
      )}
    </Card>
  )
}
