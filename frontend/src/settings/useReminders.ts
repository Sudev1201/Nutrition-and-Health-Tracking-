import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { SavedProfile } from '../onboarding/useProfile'
import type { MealTimeSetting, ReminderChange, ReminderSettings } from './types'

/*
 * The key the profile wizard also invalidates: a profile save can switch a
 * snack on or off, which adds or removes its reminder here.
 */
const REMINDERS_KEY = ['settings', 'reminders'] as const

export function useReminders() {
  return useQuery({
    queryKey: REMINDERS_KEY,
    queryFn: () => api.get<ReminderSettings>('/settings/reminders'),
    retry: false,
  })
}

/**
 * The cached profile, with the reminder switches as the server now has them.
 *
 * The profile form sends every slot's `reminder_on` back with a save, from the
 * profile it last read. Left stale, that copy would switch a reminder turned off
 * here back on at the next profile save.
 */
function withReminders(profile: SavedProfile, slots: MealTimeSetting[]): SavedProfile {
  const switches = new Map<string, boolean>(slots.map((item) => [item.slot, item.reminder_on]))
  const rows = new Set(profile.meal_times.map((item) => item.slot))
  return {
    ...profile,
    meal_times: [
      ...profile.meal_times.map((item) => ({
        ...item,
        reminder_on: switches.get(item.slot) ?? item.reminder_on,
      })),
      // A profile saved before meal times existed has no row for a slot until a
      // switch here creates one, at the time the server reports.
      ...slots
        .filter((item) => !rows.has(item.slot))
        .map((item) => ({ ...item, is_enabled: true })),
    ],
  }
}

export function useSetReminder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (change: ReminderChange) =>
      api.patch<ReminderSettings>('/settings/reminders', change),
    onSuccess: (settings) => {
      // The answer is the whole screen's state, so there is nothing to refetch.
      queryClient.setQueryData(REMINDERS_KEY, settings)
      queryClient.setQueryData<SavedProfile | null>(['profile'], (profile) =>
        profile ? withReminders(profile, settings.slots) : profile,
      )
    },
  })
}
