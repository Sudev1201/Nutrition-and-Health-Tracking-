import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { SLOT_LABELS } from '../log/types'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Toggle } from '../ui/fields'
import { EmptyState, Skeleton } from '../ui/feedback'
import {
  usePushKey,
  usePushSupport,
  useThisDevice,
  useTurnOffThisDevice,
  useTurnOnThisDevice,
} from './usePush'
import type { PushSupport } from './usePush'
import { useReminders, useSetReminder } from './useReminders'

const PROFILE_LINK =
  'inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 ' +
  'text-sm font-medium text-surface'

const NOT_SET_UP = 'Reminders are not set up on this server'

/** Why this browser cannot take reminders, when it cannot. */
const UNAVAILABLE: Record<Exclude<PushSupport, 'ready'>, { title: string; detail: string }> = {
  unsupported: {
    title: 'This browser can’t show reminders',
    detail:
      'Reminders arrive as notifications, which this browser doesn’t support. Chrome, ' +
      'Edge, Firefox and Safari do, and so does this app installed on a phone.',
  },
  'needs-install': {
    title: 'Add this app to your home screen first',
    detail:
      'On an iPhone or iPad, iOS only delivers web notifications to installed apps. Tap ' +
      'Share, then Add to Home Screen, and open the app from there to turn reminders on.',
  },
  'dev-worker': {
    title: 'Reminders can’t be turned on from this page',
    detail:
      'This page isn’t running under the app’s own service worker, which is what receives ' +
      'reminders. If the app has only just loaded, reload the page. In development the ' +
      'mock worker takes its place, so reminders need a production build.',
  },
}

const NO_PROFILE =
  'Reminders go out at the meal times in your profile, so there is nothing to remind you ' +
  'about until you have told us about yourself.'

function isNotSetUp(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503
}

function Message({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <>
      <p className="mt-1 text-sm font-medium">{title}</p>
      {children !== undefined && <p className="mt-1 text-sm text-text-muted">{children}</p>}
    </>
  )
}

/** This browser, under the production worker: say where it stands, and offer the switch. */
function ReadyDevice() {
  const key = usePushKey()
  const device = useThisDevice()
  const turnOn = useTurnOnThisDevice()
  const turnOff = useTurnOffThisDevice()

  if (key.isPending || device.isPending) return <Skeleton className="mt-2 h-11 w-full" />
  if (isNotSetUp(key.error)) {
    return (
      <Message title={NOT_SET_UP}>
        The server has no push keys, so it has nothing to send reminders with. Your meal times
        and the switches below are still saved.
      </Message>
    )
  }
  if (key.isError || device.isError) {
    return (
      <p role="alert" className="mt-1 text-sm text-above-limit">
        Whether reminders can reach this device could not be checked. Please try again.
      </p>
    )
  }
  if (device.data === 'blocked') {
    return (
      <Message title="Notifications are blocked for this app">
        This browser has been told not to show its notifications. Allow them in the site
        settings, then come back here to turn reminders on.
      </Message>
    )
  }
  if (device.data === 'on') {
    return (
      <>
        <Message title="Reminders are on for this device" />
        <Button
          variant="quiet"
          className="mt-2 px-0"
          disabled={turnOff.isPending}
          onClick={() => turnOff.mutate()}
        >
          Turn off on this device
        </Button>
      </>
    )
  }
  return (
    <>
      <p className="mt-1 text-sm text-text-muted">
        The whole app rests on logging after each meal, so a nudge at the right time matters.
        You’ll be asked to allow notifications.
      </p>
      <Button
        variant="primary"
        className="mt-3"
        disabled={turnOn.isPending}
        // Straight from the tap: Safari only shows the permission prompt from inside one.
        onClick={() => turnOn.mutate()}
      >
        Turn on reminders on this device
      </Button>
      {turnOn.isError && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {isNotSetUp(turnOn.error)
            ? NOT_SET_UP
            : 'Reminders could not be turned on for this device. Please try again.'}
        </p>
      )}
    </>
  )
}

function devicesLine(devices: number): string {
  if (devices === 0) return 'No device has reminders turned on for your account yet.'
  return `Reminders go to ${devices} ${devices === 1 ? 'device' : 'devices'} on your account.`
}

function ThisDevice({ devices }: { devices: number }) {
  const support = usePushSupport()
  const state = support.data

  return (
    <Card>
      <CardTitle>This device</CardTitle>
      {state === undefined ? (
        <Skeleton className="mt-2 h-11 w-full" />
      ) : state === 'ready' ? (
        <ReadyDevice />
      ) : (
        <Message title={UNAVAILABLE[state].title}>{UNAVAILABLE[state].detail}</Message>
      )}
      <p className="mt-3 text-xs text-text-muted">{devicesLine(devices)}</p>
    </Card>
  )
}

export function RemindersScreen() {
  const reminders = useReminders()
  const setReminder = useSetReminder()

  if (reminders.isPending) return <Skeleton className="h-64 w-full" />

  // A 404 means there is no profile yet, and so no meal times to remind about.
  if (reminders.error instanceof ApiError && reminders.error.status === 404) {
    return (
      <EmptyState
        title="Let’s set up your meal times"
        description={NO_PROFILE}
        action={
          <Link to="/profile/about" className={PROFILE_LINK}>
            Set up your profile
          </Link>
        }
      />
    )
  }
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
      <ThisDevice devices={data.devices} />

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
                slot.weekend_time === null ? undefined : `Weekends at ${slot.weekend_time}`
              }
              checked={slot.reminder_on}
              // The answer replaces every switch, so a second change waits for the first.
              disabled={setReminder.isPending}
              onChange={(on) => setReminder.mutate({ slot: slot.slot, reminder_on: on })}
            />
          ))}
        </div>

        {setReminder.isError && (
          <p role="alert" className="mt-2 text-sm text-above-limit">
            That reminder could not be changed. Please try again.
          </p>
        )}

        <p className="mt-2 text-xs text-text-muted">
          A reminder goes out at a slot’s time if nothing is logged or skipped for it yet, and
          never once you have. The mid-morning snack is off by default, since it’s optional.
        </p>
        <Link
          to="/profile/mealtimes"
          className="mt-1 inline-flex min-h-11 items-center text-sm text-accent underline"
        >
          Change your meal times
        </Link>
      </Card>
    </section>
  )
}
