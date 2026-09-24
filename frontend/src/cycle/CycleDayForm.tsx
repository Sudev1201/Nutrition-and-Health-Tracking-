import { useState } from 'react'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox, Field, Select, TextInput } from '../ui/fields'
import { FLOWS, FLOW_LABELS, SYMPTOMS, SYMPTOM_LABELS } from './types'
import type { CycleDay, Flow, Symptom } from './types'
import { useSaveCycleDay } from './useCycle'

/** The screen only shows the last 90 days, so nothing older can be reviewed once saved. */
const HISTORY_DAYS = 89

function minLoggableDate(): string {
  const [year, month, day] = todayIso().split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCDate(date.getUTCDate() - HISTORY_DAYS)
  return date.toISOString().slice(0, 10)
}

function findDay(date: string, days: CycleDay[]): CycleDay | undefined {
  return days.find((day) => day.date === date)
}

/**
 * Identifies a day's content, not just its date, so the fields below re-seed
 * whenever the matching `CycleDay` actually changes -- for example right after a
 * save brings back the row that was just written.
 */
function dayKey(date: string, day: CycleDay | undefined): string {
  return day === undefined ? date : `${date}:${day.flow ?? ''}:${day.symptoms.join(',')}`
}

/**
 * One day at a time: bleeding (or none) and symptoms. A symptom can be logged on
 * a day without bleeding, because PMS comes before a period, not during it.
 *
 * `PUT /cycle/days/{date}` replaces the whole day, so picking a date that already
 * has an entry must show what is already logged -- otherwise saving a new flow
 * would silently delete symptoms (and the coaching that depends on them).
 */
export function CycleDayForm({ days }: { days: CycleDay[] }) {
  const [date, setDate] = useState(todayIso)
  const existing = findDay(date, days)

  return (
    <DayFields
      key={dayKey(date, existing)}
      date={date}
      onDateChange={setDate}
      existing={existing}
    />
  )
}

function DayFields({
  date,
  onDateChange,
  existing,
}: {
  date: string
  onDateChange: (date: string) => void
  existing: CycleDay | undefined
}) {
  const save = useSaveCycleDay()
  const [flow, setFlow] = useState<Flow | ''>(existing?.flow ?? '')
  const [symptoms, setSymptoms] = useState<Symptom[]>(existing?.symptoms ?? [])

  const empty = flow === '' && symptoms.length === 0

  function toggle(symptom: Symptom, checked: boolean) {
    setSymptoms((current) =>
      checked ? [...current, symptom] : current.filter((item) => item !== symptom),
    )
  }

  return (
    <Card>
      <CardTitle>Log a day</CardTitle>
      <div className="mt-2 grid gap-x-3 sm:grid-cols-2">
        <Field label="Date">
          {(props) => (
            <TextInput
              {...props}
              type="date"
              value={date}
              min={minLoggableDate()}
              max={todayIso()}
              onChange={(event) => onDateChange(event.target.value)}
            />
          )}
        </Field>
        <Field label="Bleeding">
          {(props) => (
            <Select
              {...props}
              value={flow}
              onChange={(event) => setFlow(event.target.value as Flow | '')}
            >
              <option value="">None</option>
              {FLOWS.map((item) => (
                <option key={item} value={item}>
                  {FLOW_LABELS[item]}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">Symptoms</legend>
        {SYMPTOMS.map((symptom) => (
          <Checkbox
            key={symptom}
            label={SYMPTOM_LABELS[symptom]}
            checked={symptoms.includes(symptom)}
            onChange={(event) => toggle(symptom, event.target.checked)}
          />
        ))}
      </fieldset>
      <Button
        variant="primary"
        className="mt-3"
        disabled={empty || date === '' || save.isPending}
        onClick={() => save.mutate({ date, day: { flow: flow === '' ? null : flow, symptoms } })}
      >
        {existing === undefined ? 'Save day' : 'Update day'}
      </Button>
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          That day could not be saved. Please try again.
        </p>
      )}
    </Card>
  )
}
