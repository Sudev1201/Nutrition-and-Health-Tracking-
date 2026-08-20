import { AlertTriangle, Pencil } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { ApiError } from '../lib/api'
import { SLOT_LABELS, SLOT_ORDER } from '../log/types'
import type { MealSlot } from '../log/types'
import { useProfile } from '../onboarding/useProfile'
import type { SavedProfile } from '../onboarding/useProfile'
import {
  ACTIVITY_LABELS,
  CONDITION_LABELS,
  DIET_LABELS,
  GOAL_LABELS,
  PACE_LABELS,
  SEX_LABELS,
} from '../onboarding/types'
import type { ActivityLevel, ConditionCode, DietType, Goal, Pace, Sex } from '../onboarding/types'
import { STEP_TITLES, hasConditionConflict } from '../onboarding/validation'
import type { StepId } from '../onboarding/validation'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { EmptyState, Skeleton } from '../ui/feedback'
import { NotSet, SummaryList, SummaryRow } from '../ui/SummaryRow'

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

/**
 * One section of the questionnaire, read back.
 *
 * `aria-label` on the section makes each one addressable as a landmark, which is
 * what lets someone jump to "Health conditions" rather than tabbing through
 * every answer above it.
 */
function Section({ step, children }: { step: StepId; children: ReactNode }) {
  const title = STEP_TITLES[step]

  return (
    <Card>
      <section aria-label={title}>
        <div className="mb-1 flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-medium text-text-muted">{title}</h3>
          {/*
            Editing is per section rather than one "Edit profile" button, because
            correcting a weight should not walk someone through all eight steps
            again.
          */}
          <Link
            to={`/profile/${step}`}
            aria-label={`Edit ${title}`}
            className="inline-flex min-h-11 items-center gap-1 text-sm text-accent"
          >
            <Pencil className="size-3.5" aria-hidden="true" />
            Edit
          </Link>
        </div>
        {children}
      </section>
    </Card>
  )
}

function Chips({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <NotSet>{empty}</NotSet>

  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item}>
          <Badge tone="neutral">{item}</Badge>
        </li>
      ))}
    </ul>
  )
}

function observanceText(rule: SavedProfile['observances'][number]): string {
  if (rule.label !== '') return rule.label
  if (rule.kind === 'weekday' && rule.weekday !== null) return `Every ${WEEKDAYS[rule.weekday]}`
  if (rule.kind === 'date_range') return `${rule.start_date ?? '?'} to ${rule.end_date ?? '?'}`
  return rule.start_date ?? 'A day'
}

export function ProfileScreen() {
  const profile = useProfile()

  if (profile.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  // `useProfile` maps a 404 to null, which means "not onboarded yet" — a
  // different thing from a failure, and the only case where sending someone to
  // the questionnaire is the right answer.
  if (profile.data === null) {
    return (
      <EmptyState
        title="No profile yet"
        description="Answer a few questions and the app can work out your targets."
        action={
          <Link
            to="/profile/about"
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-sm font-medium text-surface"
          >
            Set up your profile
          </Link>
        }
      />
    )
  }

  if (profile.isError || profile.data === undefined) {
    const status = profile.error instanceof ApiError ? profile.error.status : null
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your profile could not be loaded{status !== null && ` (${status})`}. Please try again.
      </p>
    )
  }

  const data = profile.data
  const conflict = hasConditionConflict(data.conditions)
  const mealTimes = new Map(data.meal_times.map((item) => [item.slot, item]))

  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold">Your profile</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <Section step="about">
          <SummaryList>
            <SummaryRow label="Sex">
              {data.sex === null ? <NotSet /> : SEX_LABELS[data.sex as Sex]}
            </SummaryRow>
            <SummaryRow label="Age">{data.age} years</SummaryRow>
            {/*
              Weight but no height, deliberately: the ICMR energy equations are
              weight-based and the reference heights could not be verified.
            */}
            <SummaryRow label="Weight">{data.weight_kg} kg</SummaryRow>
            <SummaryRow label="Activity level">
              {data.activity === null ? (
                <NotSet />
              ) : (
                ACTIVITY_LABELS[data.activity as ActivityLevel]
              )}
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="goal">
          <SummaryList>
            <SummaryRow label="Aiming to">
              {data.goal === null ? <NotSet /> : GOAL_LABELS[data.goal as Goal]}
            </SummaryRow>
            <SummaryRow label="Pace">
              {data.pace === null ? (
                <NotSet>Not applicable</NotSet>
              ) : (
                PACE_LABELS[data.pace as Pace]
              )}
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="diet">
          <SummaryList>
            <SummaryRow label="Diet">
              {data.diet_type === null ? <NotSet /> : DIET_LABELS[data.diet_type as DietType]}
            </SummaryRow>
            <SummaryRow
              label="Mostly rice or cereals"
              hint={
                data.cereal_dominant
                  ? 'Protein is set at 1 g/kg rather than 0.83 g/kg'
                  : undefined
              }
            >
              {data.cereal_dominant ? 'Yes' : 'No'}
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="conditions">
          {conflict && (
            <p
              role="alert"
              className="mb-2 flex gap-2 rounded-card border border-above-limit/40 bg-above-limit/5 p-2 text-xs text-above-limit"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>
                Two of these conditions pull in opposite directions, so neither one’s limits are
                being applied. Worth raising with your doctor.
              </span>
            </p>
          )}
          <SummaryList>
            <SummaryRow label="Conditions">
              <Chips
                items={data.conditions.map((code) => CONDITION_LABELS[code as ConditionCode])}
                empty="None recorded"
              />
            </SummaryRow>
            <SummaryRow label="Medications">
              <Chips
                items={data.medications.map((item) => `${item.name} · ${item.time}`)}
                empty="None recorded"
              />
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="observance">
          <SummaryList>
            <SummaryRow label="Vegetarian days">
              <Chips
                items={data.observances.map(observanceText)}
                empty="No recurring days"
              />
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="preferences">
          <SummaryList>
            <SummaryRow label="Foods you like">
              <Chips items={data.favourites.map((item) => item.label)} empty="None listed" />
            </SummaryRow>
            <SummaryRow label="Foods you avoid">
              <Chips items={data.avoided.map((item) => item.label)} empty="None listed" />
            </SummaryRow>
          </SummaryList>
        </Section>

        <Section step="mealtimes">
          <SummaryList>
            {SLOT_ORDER.map((slot: MealSlot) => {
              const meal = mealTimes.get(slot)
              return (
                <SummaryRow
                  key={slot}
                  label={SLOT_LABELS[slot]}
                  hint={
                    meal?.weekend_time !== null && meal?.weekend_time !== undefined
                      ? `${meal.weekend_time} at weekends`
                      : undefined
                  }
                >
                  {/* A snack switched off is shown rather than hidden, so it is
                      obvious why the diary has four slots and not five. */}
                  {meal !== undefined && !meal.is_enabled ? (
                    <NotSet>Not part of your day</NotSet>
                  ) : (
                    (meal?.time ?? <NotSet />)
                  )}
                </SummaryRow>
              )
            })}
          </SummaryList>
        </Section>

        <Section step="usual">
          <SummaryList>
            {data.usual_intake.length === 0 ? (
              <SummaryRow label="A usual day">
                <NotSet>Not described yet</NotSet>
              </SummaryRow>
            ) : (
              data.usual_intake.map((item, index) => (
                <SummaryRow key={`${item.slot}-${index}`} label={SLOT_LABELS[item.slot]}>
                  {item.label} · {item.grams} g
                </SummaryRow>
              ))
            )}
          </SummaryList>
        </Section>
      </div>
    </section>
  )
}
