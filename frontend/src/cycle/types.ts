/**
 * CONTRACT for `/cycle` — plan 7.
 *
 * Amended from the plan 2.5 proposal where it could not express the spec: the
 * screen can now log days with symptoms (coaching is symptom-driven, not
 * calendar-driven), answer the heavy-bleeding screening questions, and learn
 * that tracking is not offered to this profile at all.
 */

export type Flow = 'light' | 'medium' | 'heavy'

export const FLOWS: Flow[] = ['light', 'medium', 'heavy']

export const FLOW_LABELS: Record<Flow, string> = {
  light: 'Light',
  medium: 'Medium',
  heavy: 'Heavy',
}

/**
 * The symptoms the coaching responds to. There is deliberately no "cravings":
 * the perimenstrual chocolate-craving script is largely an American cultural
 * artefact, and has no place in the copy.
 */
export type Symptom = 'cramps' | 'bloating' | 'breast_tenderness' | 'low_mood'

export const SYMPTOMS: Symptom[] = ['cramps', 'bloating', 'breast_tenderness', 'low_mood']

export const SYMPTOM_LABELS: Record<Symptom, string> = {
  cramps: 'Cramps',
  bloating: 'Bloating',
  breast_tenderness: 'Breast tenderness',
  low_mood: 'Low mood',
}

export interface CycleDay {
  date: string
  /** Null on a day with symptoms but no bleeding. */
  flow: Flow | null
  symptoms: Symptom[]
}

export interface CycleDayInput {
  flow: Flow | null
  symptoms: Symptom[]
}

/**
 * How well supported a piece of advice is. Rendered as a visible label, because
 * the spec commits to evidence being "labelled, not laundered" — traditional
 * practice must never be presented as established nutrition, nor a sound
 * mechanism (`mechanistic`) as trial evidence.
 */
export type EvidenceGrade = 'strong' | 'moderate' | 'mechanistic' | 'low' | 'traditional'

export interface CoachingNote {
  id: string
  title: string
  body: string
  evidence: EvidenceGrade
}

/** The validated heavy-bleeding screening questions. */
export interface ScreeningAnswers {
  soaks_within_two_hours: boolean
  longer_than_seven_days: boolean
  large_clots: boolean
  flooding: boolean
}

export interface Screening extends ScreeningAnswers {
  answered_on: string
}

export type IneligibleReason = 'not-female' | 'postmenopausal'

export interface CycleState {
  /** Tracking is offered to a woman's profile that is not postmenopausal. */
  eligible: boolean
  ineligible_reason: IneligibleReason | null
  /** Off unless the user turns it on, and private within a household by default. */
  enabled: boolean
  /** Something is stored, even while hidden, so it can still be erased. */
  has_history: boolean
  /** The first day of the latest logged bleed. Never a prediction. */
  last_period_start: string | null
  /** Logged days, newest first, the last 90 days. Empty while tracking is off. */
  days: CycleDay[]
  screening: Screening | null
  coaching: CoachingNote[]
  /**
   * Set when a screening answer is yes, or when more than seven consecutive days
   * of bleeding were logged. This produces a clinician referral and NEVER a
   * nutrient-target change: about 1 in 5 adolescents with heavy bleeding has an
   * underlying bleeding disorder, and answering with dietary advice would
   * suppress a real signal.
   */
  referral: { reason: string } | null
}
