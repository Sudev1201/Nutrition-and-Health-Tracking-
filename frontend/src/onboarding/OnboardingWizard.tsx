import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Skeleton } from '../ui/feedback'
import {
  AboutStep,
  ConditionsStep,
  DietStep,
  GoalStep,
  MealTimesStep,
  ObservanceStep,
  PreferencesStep,
} from './steps'
import { UsualIntakeStep } from './UsualIntakeStep'
import type { StepProps } from './steps'
import type { OnboardingAnswers } from './types'
import { answersFromProfile, useProfile } from './useProfile'
import { emptyAnswers, STEP_ORDER, STEP_TITLES, validateStep } from './validation'
import type { StepId } from './validation'

const STEP_COMPONENTS: Record<StepId, (props: StepProps) => React.ReactElement> = {
  about: AboutStep,
  goal: GoalStep,
  diet: DietStep,
  conditions: ConditionsStep,
  observance: ObservanceStep,
  preferences: PreferencesStep,
  mealtimes: MealTimesStep,
  usual: UsualIntakeStep,
}

function useSaveProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (answers: OnboardingAnswers) => api.put('/profile', answers),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      // First targets are computed from the profile, so they change too.
      queryClient.invalidateQueries({ queryKey: ['targets'] })
    },
  })
}

export function OnboardingWizard({
  onDone,
  startStep,
}: {
  onDone?: () => void
  /**
   * Open at this step instead of the first one, so the profile summary's
   * per-section Edit links land on the section the user asked for rather than
   * walking them through all eight again.
   */
  startStep?: StepId
}) {
  const [index, setIndex] = useState(() => {
    if (startStep === undefined) return 0
    const found = STEP_ORDER.indexOf(startStep)
    // An unrecognised step falls back to the beginning rather than rendering
    // nothing, so a stale or hand-typed URL cannot produce a blank screen.
    return found === -1 ? 0 : found
  })
  const [answers, setAnswers] = useState<OnboardingAnswers>(emptyAnswers)
  const [error, setError] = useState<string | null>(null)
  const saveProfile = useSaveProfile()
  const navigate = useNavigate()
  const profile = useProfile()

  // Prefill once the saved profile arrives, so revisiting this screen edits the
  // existing answers rather than presenting a blank form that would overwrite
  // them. Keyed on the fetched object, so a later refetch does not clobber
  // edits in progress.
  useEffect(() => {
    if (profile.data) setAnswers(answersFromProfile(profile.data))
  }, [profile.data])

  const step = STEP_ORDER[index]
  const StepBody = STEP_COMPONENTS[step]
  const isLast = index === STEP_ORDER.length - 1

  function update(changes: Partial<OnboardingAnswers>) {
    setAnswers((current) => ({ ...current, ...changes }))
    // Clear a stale message the moment the user starts fixing what it named.
    setError(null)
  }

  function next() {
    const problem = validateStep(step, answers)
    if (problem !== null) {
      setError(problem)
      return
    }

    if (isLast) {
      saveProfile.mutate(answers, {
        onSuccess: () => {
          // Targets exist now, so Today has something to show.
          if (onDone) onDone()
          else navigate('/')
        },
      })
      return
    }
    setIndex(index + 1)
  }

  if (profile.isPending) return <Skeleton className="h-96 w-full" />

  return (
    <section className="mx-auto max-w-xl">
      <p className="text-xs text-text-muted">
        Step {index + 1} of {STEP_ORDER.length}
      </p>
      <h2 className="mt-0.5 mb-1 text-xl font-semibold">{STEP_TITLES[step]}</h2>

      <div
        className="mb-4 h-1 overflow-hidden rounded-full bg-border"
        role="progressbar"
        aria-label="Onboarding progress"
        aria-valuenow={index + 1}
        aria-valuemin={1}
        aria-valuemax={STEP_ORDER.length}
      >
        <div
          className="h-full bg-accent"
          style={{ width: `${((index + 1) / STEP_ORDER.length) * 100}%` }}
        />
      </div>

      <Card>
        <StepBody answers={answers} update={update} />
      </Card>

      {error !== null && (
        <p role="alert" className="mt-3 text-sm text-above-limit">
          {error}
        </p>
      )}

      {saveProfile.isError && (
        <p role="alert" className="mt-3 text-sm text-above-limit">
          Your profile could not be saved. Please try again.
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <Button disabled={index === 0} onClick={() => setIndex(index - 1)}>
          Back
        </Button>
        <Button
          variant="primary"
          className="flex-1"
          disabled={saveProfile.isPending}
          onClick={next}
        >
          {isLast ? (profile.data ? 'Save changes' : 'Finish') : 'Continue'}
        </Button>
      </div>
    </section>
  )
}
