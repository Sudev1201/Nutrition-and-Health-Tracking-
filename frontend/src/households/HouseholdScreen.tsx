import { useState } from 'react'
import { useSession } from '../auth/useSession'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Checkbox, TextInput } from '../ui/fields'
import { Skeleton } from '../ui/feedback'
import {
  useAcceptInvite,
  useCreateHousehold,
  useHousehold,
  useInvite,
  useLeaveHousehold,
  useUpdateVisibility,
} from './useHousehold'

function NoHousehold() {
  const createHousehold = useCreateHousehold()
  const acceptInvite = useAcceptInvite()
  const [name, setName] = useState('')
  const [token, setToken] = useState('')

  return (
    <section>
      <h2 className="text-xl font-semibold">You're tracking on your own</h2>
      <p className="mt-1 max-w-prose text-sm text-text-muted">
        That's the full app — targets, logging, plans and reports are all yours and need
        nothing else. A household is only worth setting up if you cook with other people and
        want to share recipes and see each other's progress.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle>Start a household</CardTitle>
          <TextInput
            className="mt-2"
            aria-label="Household name"
            placeholder="Household name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button
            variant="primary"
            block
            className="mt-2"
            disabled={name.trim() === '' || createHousehold.isPending}
            onClick={() => createHousehold.mutate(name.trim())}
          >
            Create household
          </Button>
        </Card>

        <Card>
          <CardTitle>Join one you were invited to</CardTitle>
          <TextInput
            className="mt-2"
            aria-label="Invite token"
            placeholder="Paste your invite token"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <Button
            block
            className="mt-2"
            disabled={token.trim() === '' || acceptInvite.isPending}
            onClick={() => acceptInvite.mutate(token.trim())}
          >
            Join household
          </Button>
          {acceptInvite.isError && (
            <p role="alert" className="mt-2 text-sm text-above-limit">
              That invite is not valid or has expired.
            </p>
          )}
        </Card>
      </div>
    </section>
  )
}

export function HouseholdScreen() {
  const { data: household, isLoading } = useHousehold()
  const { user } = useSession()
  const invite = useInvite()
  const leaveHousehold = useLeaveHousehold()
  const updateVisibility = useUpdateVisibility()
  const [email, setEmail] = useState('')

  if (isLoading) return <Skeleton className="h-40 w-full" />
  if (!household) return <NoHousehold />

  // Member order comes from the membership query and is not stable, so the
  // current user is found by id. Reading members[0] showed -- and toggled -- the
  // first member's sharing settings for everyone else in the household.
  const me = household.members.find((member) => member.user_id === user?.id)

  return (
    <section>
      <h2 className="text-xl font-semibold">{household.name}</h2>

      <ul className="mt-4 divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
        {household.members.map((member) => (
          <li key={member.user_id} className="flex items-center justify-between gap-3 p-3">
            <div className="min-w-0">
              <p className="truncate font-medium">
                {member.name}
                {member.user_id === user?.id && (
                  <span className="ml-2 text-xs font-normal text-text-muted">you</span>
                )}
              </p>
              <p className="truncate text-sm text-text-muted">{member.email}</p>
            </div>
            <Badge tone={member.share_progress ? 'accent' : 'neutral'}>
              {member.share_progress ? 'Progress shared' : 'Progress private'}
            </Badge>
          </li>
        ))}
      </ul>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card>
          <CardTitle>Invite someone</CardTitle>
          <TextInput
            className="mt-2"
            type="email"
            aria-label="Email to invite"
            placeholder="their@email.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Button
            block
            className="mt-2"
            disabled={email.trim() === '' || invite.isPending}
            onClick={() => invite.mutate(email.trim())}
          >
            Create invite link
          </Button>
          {invite.data && (
            <p className="mt-2 text-sm text-text-muted">
              Share this token with {invite.data.email}:{' '}
              <code className="break-all">{invite.data.token}</code>
            </p>
          )}
        </Card>

        <Card>
          <CardTitle>What you share</CardTitle>
          <div className="mt-1">
            <Checkbox
              label="Share my daily progress with the household"
              checked={me?.share_progress ?? true}
              onChange={(event) =>
                updateVisibility.mutate({ share_progress: event.target.checked })
              }
            />
            <Checkbox
              label="Share my health details (conditions, weight, cycle)"
              checked={me?.share_health ?? false}
              onChange={(event) =>
                updateVisibility.mutate({ share_health: event.target.checked })
              }
            />
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Conditions, labs, medications, weight and cycle data stay private unless you turn
            this on.
          </p>
        </Card>
      </div>

      <div className="mt-8 border-t border-border pt-4">
        <Button
          variant="danger"
          disabled={leaveHousehold.isPending}
          onClick={() => leaveHousehold.mutate()}
        >
          Leave household
        </Button>
        <p className="mt-1 text-xs text-text-muted">
          You'll go back to tracking on your own. Your logs, targets and plans stay exactly as
          they are.
        </p>
      </div>
    </section>
  )
}
