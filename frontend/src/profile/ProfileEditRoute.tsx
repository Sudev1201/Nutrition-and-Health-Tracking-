import { useNavigate, useParams } from 'react-router-dom'
import { OnboardingWizard } from '../onboarding/OnboardingWizard'
import type { StepId } from '../onboarding/validation'

/**
 * `/profile/:step` — the questionnaire opened at one section.
 *
 * Saving returns to the summary rather than to Today, because the user came from
 * the summary to change one thing and expects to land back where they can see
 * whether it took.
 */
export function ProfileEditRoute() {
  const { step } = useParams<{ step: string }>()
  const navigate = useNavigate()

  return (
    <OnboardingWizard
      startStep={step as StepId | undefined}
      onDone={() => navigate('/profile')}
    />
  )
}
