import { useState } from 'react'
import { todayIso } from '../today/useToday'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox, Field, Select, TextInput } from '../ui/fields'
import { FLOWS, FLOW_LABELS, SYMPTOMS, SYMPTOM_LABELS } from './types'
import type { Flow, Symptom } from './types'
import { useSaveCycleDay } from './useCycle'

/**
 * One day at a time: bleeding (or none) and symptoms. A symptom can be logged on
 * a day without bleeding, because PMS comes before a period, not during it.
 */
export function CycleDayForm() {
  const save = useSaveCycleDay()
  const [date, setDate] = useState(todayIso)
  const [flow, setFlow] = useState<Flow | ''>('')
  const [symptoms, setSymptoms] = useState<Symptom[]>([])

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
              max={todayIso()}
              onChange={(event) => setDate(event.target.value)}
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
        onClick={() =>
          save.mutate(
            { date, day: { flow: flow === '' ? null : flow, symptoms } },
            {
              onSuccess: () => {
                setFlow('')
                setSymptoms([])
              },
            },
          )
        }
      >
        Save day
      </Button>
      {save.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          That day could not be saved. Please try again.
        </p>
      )}
    </Card>
  )
}
