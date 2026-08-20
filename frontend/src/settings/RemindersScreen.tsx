import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { SLOT_LABELS } from '../log/types'
import type { MealSlot } from '../log/types'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { DemoDataBanner, Skeleton } from '../ui/feedback'
import type { ReminderSettings } from './types'

function useReminders() {
  return useQuery({
    queryKey: ['settings', 'reminders'],
    queryFn: () => api.get<ReminderSettings>('/settings/reminders'),
    retry: false,
  })
}

function useSetReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ slot, on }: { slot: MealSlot; on: boolean }) =>
      api.patch('/settings/reminders', { slot, reminder_on: on }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings', 'reminders'] }),
  })
}

export function RemindersScreen() {
  const reminders = useReminders()
  const setReminder = useSetReminder()

  if (reminders.isPending) return <Skeleton className="h-64 w-full" />
  if (reminders.isError || reminders.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your reminder settings could not be loaded. Please try again.
      </p>
    )
  }

  const data = reminders.data

  return (
    <section className="space-y-4">
      <DemoDataBanner endpoint="GET /settings/reminders" />

      {!data.push_granted && (
        <Card>
          <CardTitle>Notifications are off</CardTitle>
          <p className="mt-1 text-sm text-text-muted">
            The whole app rests on logging after each meal, so a nudge at the right time
            matters. On an iPhone you’ll need to add this app to your home screen first —
            iOS only delivers web notifications to installed apps.
          </p>
        </Card>
      )}

      <Card>
        <CardTitle>Meal times and reminders</CardTitle>
        <p className="mt-1 mb-2 text-sm text-text-muted">
          These times also make your medication windows concrete — knowing breakfast is at 8:00
          is what lets the planner check the 60-minute levothyroxine gap.
        </p>

        <div className="divide-y divide-border">
          {data.slots.map((slot) => (
            <Toggle
              key={slot.slot}
              label={`${SLOT_LABELS[slot.slot]} · ${slot.time}`}
              description={
                slot.weekend_time === null
                  ? undefined
                  : `Weekends at ${slot.weekend_time}`
              }
              checked={slot.reminder_on}
              onChange={(on) => setReminder.mutate({ slot: slot.slot, on })}
            />
          ))}
        </div>

        <p className="mt-2 text-xs text-text-muted">
          Reminders stop once a slot is logged, and the mid-morning snack is off by default
          since it’s optional.
        </p>
      </Card>
    </section>
  )
}
