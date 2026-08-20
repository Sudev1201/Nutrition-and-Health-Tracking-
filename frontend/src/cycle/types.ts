/** PROPOSED CONTRACT for `GET /cycle` and its POSTs — implemented by plan 7. */

export type Flow = 'light' | 'medium' | 'heavy'

export interface CycleLog {
  date: string
  flow: Flow
}

/**
 * How well supported a piece of advice is. Rendered as a visible label, because
 * the spec commits to evidence being "labelled, not laundered" — traditional
 * practice must never be presented as established nutrition.
 */
export type EvidenceGrade = 'strong' | 'moderate' | 'low' | 'traditional'

export interface CoachingNote {
  id: string
  title: string
  body: string
  evidence: EvidenceGrade
}

export interface CycleState {
  /** Off unless the user turns it on, and private within a household by default. */
  enabled: boolean
  last_period_start: string | null
  logs: CycleLog[]
  coaching: CoachingNote[]
  /**
   * Set when the validated heavy-bleeding screening questions are answered yes.
   * This produces a clinician referral and NEVER a nutrient-target change —
   * about 1 in 5 adolescents with heavy bleeding has an underlying bleeding
   * disorder, so answering with dietary advice would suppress a real signal.
   */
  referral: { reason: string } | null
}
