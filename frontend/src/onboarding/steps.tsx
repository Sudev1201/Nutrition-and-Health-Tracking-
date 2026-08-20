import { Plus, Trash2 } from 'lucide-react'
import { SLOT_LABELS } from '../log/types'
import { Button } from '../ui/Button'
import { Checkbox, Field, NumberInput, Select, TextInput, Toggle } from '../ui/fields'
import { FoodListField } from '../ui/FoodListField'
import {
  ACTIVITY_HINTS,
  ACTIVITY_LABELS,
  CONDITION_LABELS,
  DIET_LABELS,
  GOAL_LABELS,
  PACE_HINTS,
  PACE_LABELS,
  SEX_LABELS,
} from './types'
import type {
  ActivityLevel,
  ConditionCode,
  DietType,
  Goal,
  OnboardingAnswers,
  Pace,
  Sex,
} from './types'
import { OPTIONAL_SLOTS, hasConditionConflict } from './validation'

export interface StepProps {
  answers: OnboardingAnswers
  update: (changes: Partial<OnboardingAnswers>) => void
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function AboutStep({ answers, update }: StepProps) {
  return (
    <>
      <Field label="Sex" hint="ICMR publishes separate reference values for women and men.">
        {(props) => (
          <Select
            {...props}
            value={answers.sex ?? ''}
            onChange={(event) => update({ sex: event.target.value as Sex })}
          >
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(SEX_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <Field label="Age">
        {(props) => (
          <NumberInput
            {...props}
            value={answers.age}
            onChange={(event) => update({ age: event.target.value })}
            placeholder="34"
          />
        )}
      </Field>

      {/*
        Weight but no height: the ICMR energy equations are weight-based, and the
        spec found the published reference heights could not be verified against
        any primary source. Asking for one would imply precision we don't have.
      */}
      <Field label="Weight in kg" hint="Your calorie target is computed from this.">
        {(props) => (
          <NumberInput
            {...props}
            value={answers.weight_kg}
            onChange={(event) => update({ weight_kg: event.target.value })}
            placeholder="74.2"
          />
        )}
      </Field>

      <Field
        label="Activity level"
        hint="This also selects which column of the B-vitamin tables applies — the widely-quoted figures are the moderate one."
      >
        {(props) => (
          <Select
            {...props}
            value={answers.activity ?? ''}
            onChange={(event) => update({ activity: event.target.value as ActivityLevel })}
          >
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(ACTIVITY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label} — {ACTIVITY_HINTS[value as ActivityLevel]}
              </option>
            ))}
          </Select>
        )}
      </Field>
    </>
  )
}

export function GoalStep({ answers, update }: StepProps) {
  return (
    <>
      <Field label="What are you aiming for?">
        {(props) => (
          <Select
            {...props}
            value={answers.goal ?? ''}
            onChange={(event) =>
              update({
                goal: event.target.value as Goal,
                pace: event.target.value === 'maintain' ? null : answers.pace,
              })
            }
          >
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(GOAL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      {answers.goal !== null && answers.goal !== 'maintain' && (
        <Field label="Pace" hint="Gentler changes are easier to hold and safer to sustain.">
          {(props) => (
            <Select
              {...props}
              value={answers.pace ?? ''}
              onChange={(event) => update({ pace: event.target.value as Pace })}
            >
              <option value="" disabled>
                Choose…
              </option>
              {Object.entries(PACE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label} — {PACE_HINTS[value as Pace]}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
    </>
  )
}

export function DietStep({ answers, update }: StepProps) {
  return (
    <>
      <Field label="How do you eat?">
        {(props) => (
          <Select
            {...props}
            value={answers.diet_type ?? ''}
            onChange={(event) => update({ diet_type: event.target.value as DietType })}
          >
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(DIET_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <Toggle
        label="My meals are mostly rice or other cereals"
        description="With limited pulses, curd or milk. ICMR sets protein at 1 g/kg rather than 0.83 g/kg for a cereal-dominant diet, because the protein quality is lower. You can change this later, and once you have logged enough days the app can work it out from what you actually eat."
        checked={answers.cereal_dominant}
        onChange={(checked) => update({ cereal_dominant: checked })}
      />
    </>
  )
}

export function ConditionsStep({ answers, update }: StepProps) {
  const conflict = hasConditionConflict(answers.conditions)

  function toggleCondition(code: ConditionCode, on: boolean) {
    update({
      conditions: on
        ? [...answers.conditions, code]
        : answers.conditions.filter((existing) => existing !== code),
    })
  }

  return (
    <>
      <p className="mb-3 text-sm text-text-muted">
        Only if a clinician has diagnosed them. This app is not medical advice and does not
        replace your doctor.
      </p>

      <fieldset className="mb-4">
        <legend className="mb-1 text-sm font-medium">Conditions</legend>
        {(Object.keys(CONDITION_LABELS) as ConditionCode[]).map((code) => (
          <Checkbox
            key={code}
            label={CONDITION_LABELS[code]}
            checked={answers.conditions.includes(code)}
            onChange={(event) => toggleCondition(code, event.target.checked)}
          />
        ))}
      </fieldset>

      {conflict && (
        <p
          role="alert"
          className="mb-4 rounded-card border border-above-limit/40 bg-above-limit/5 p-3 text-sm text-above-limit"
        >
          Those two conditions call for opposite advice. The app will not average them — it
          will flag the conflict and ask you to talk to your clinician.
        </p>
      )}

      <fieldset>
        <legend className="mb-1 text-sm font-medium">Medications</legend>
        <p className="mb-2 text-xs text-text-muted">
          The time matters: levothyroxine needs 60 minutes clear of any food or drink,
          including milk coffee, and 4 hours clear of calcium and iron.
        </p>

        {answers.medications.map((medication, index) => (
          <div key={index} className="mb-2 flex items-center gap-2">
            <TextInput
              aria-label={`Medication ${index + 1} name`}
              placeholder="Levothyroxine"
              value={medication.name}
              onChange={(event) =>
                update({
                  medications: answers.medications.map((existing, position) =>
                    position === index ? { ...existing, name: event.target.value } : existing,
                  ),
                })
              }
            />
            <input
              type="time"
              aria-label={`Medication ${index + 1} time`}
              value={medication.time}
              onChange={(event) =>
                update({
                  medications: answers.medications.map((existing, position) =>
                    position === index ? { ...existing, time: event.target.value } : existing,
                  ),
                })
              }
              className="rounded-control border border-border bg-surface px-3 py-2"
            />
            <Button
              variant="quiet"
              aria-label={`Remove medication ${index + 1}`}
              onClick={() =>
                update({
                  medications: answers.medications.filter((_, position) => position !== index),
                })
              }
            >
              <Trash2 className="size-4" aria-hidden="true" />
            </Button>
          </div>
        ))}

        <Button
          onClick={() =>
            update({ medications: [...answers.medications, { name: '', time: '' }] })
          }
        >
          <Plus className="size-4" aria-hidden="true" />
          Add a medication
        </Button>
      </fieldset>
    </>
  )
}

export function ObservanceStep({ answers, update }: StepProps) {
  const selectedWeekdays = answers.observances
    .filter((rule) => rule.kind === 'weekday')
    .map((rule) => rule.weekday)

  function toggleWeekday(index: number, on: boolean) {
    update({
      observances: on
        ? [
            ...answers.observances,
            {
              kind: 'weekday',
              weekday: index,
              start_date: null,
              end_date: null,
              label: `${WEEKDAYS[index]}s`,
            },
          ]
        : answers.observances.filter(
            (rule) => !(rule.kind === 'weekday' && rule.weekday === index),
          ),
    })
  }

  return (
    <>
      <p className="mb-3 text-sm text-text-muted">
        Days you don’t eat non-vegetarian food. On these days egg counts as non-vegetarian too,
        so the planner leans on dairy and pulses to keep protein and B12 up — and makes up any
        shortfall over the days that follow.
      </p>

      <fieldset>
        <legend className="mb-1 text-sm font-medium">Every week on</legend>
        {WEEKDAYS.map((weekday, index) => (
          <Checkbox
            key={weekday}
            label={weekday}
            checked={selectedWeekdays.includes(index)}
            onChange={(event) => toggleWeekday(index, event.target.checked)}
          />
        ))}
      </fieldset>

      <p className="mt-3 text-xs text-text-muted">
        Whole months such as Purattasi, fasting periods and one-off festival dates can be added
        from your profile once you’re set up.
      </p>
    </>
  )
}

export function PreferencesStep({ answers, update }: StepProps) {
  return (
    <>
      <FoodListField
        label="Foods you particularly like"
        hint="Add as many as you want. Individual items work best — curd, milk, apple, murungai keerai. The planner leans towards these."
        searchLabel="Search foods you like"
        items={answers.favourites}
        onChange={(favourites) => update({ favourites })}
      />

      {/*
        One list rather than separate "allergies" and "dislikes": the planner
        blocks both the same way, and asking someone to classify their own
        aversion as medical or not serves no purpose.
      */}
      <FoodListField
        label="Foods to avoid"
        hint="Allergies, intolerances, or anything you would simply rather not eat. These are a hard block — nothing containing them is ever suggested."
        searchLabel="Search foods to avoid"
        items={answers.avoided}
        onChange={(avoided) => update({ avoided })}
      />
    </>
  )
}


export function MealTimesStep({ answers, update }: StepProps) {
  return (
    <>
      <p className="mb-3 text-sm text-text-muted">
        Your usual times. These drive reminders, and they’re what let the planner check
        medication windows against real meals.
      </p>

      {answers.meal_times.map((meal, index) => (
        <div key={meal.slot} className="mb-3">
          <p className="mb-1 text-sm font-medium">{SLOT_LABELS[meal.slot]}</p>

          {/*
            Only the snacks get a switch. Four or five meals a day means one or
            two snacks; a day without lunch is a skipped lunch, recorded per day
            on the Today screen rather than as a standing preference here.
          */}
          {OPTIONAL_SLOTS.includes(meal.slot) && (
            <Toggle
              label={`Include the ${SLOT_LABELS[meal.slot].toLowerCase()}`}
              description="Turn this off if a normal day for you does not include it."
              checked={meal.is_enabled}
              onChange={(checked) =>
                update({
                  meal_times: answers.meal_times.map((existing, position) =>
                    position === index ? { ...existing, is_enabled: checked } : existing,
                  ),
                })
              }
            />
          )}

          {/* A slot that is not part of the day has no time worth asking for. */}
          {meal.is_enabled && (
          <>
          <div className="flex flex-wrap gap-2">
            <input
              type="time"
              aria-label={`${SLOT_LABELS[meal.slot]} time`}
              value={meal.time}
              onChange={(event) =>
                update({
                  meal_times: answers.meal_times.map((existing, position) =>
                    position === index ? { ...existing, time: event.target.value } : existing,
                  ),
                })
              }
              className="rounded-control border border-border bg-surface px-3 py-2"
            />
            <input
              type="time"
              aria-label={`${SLOT_LABELS[meal.slot]} weekend time`}
              value={meal.weekend_time ?? ''}
              onChange={(event) =>
                update({
                  meal_times: answers.meal_times.map((existing, position) =>
                    position === index
                      ? { ...existing, weekend_time: event.target.value || null }
                      : existing,
                  ),
                })
              }
              className="rounded-control border border-border bg-surface px-3 py-2 text-text-muted"
            />
          </div>
          <p className="mt-0.5 text-xs text-text-muted">Weekday, then weekend if it differs.</p>
          </>
          )}
        </div>
      ))}
    </>
  )
}
