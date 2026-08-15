import { useState } from 'react'
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
    <section className="mx-auto max-w-3xl p-6">
      <h2 className="text-xl font-semibold">You're tracking on your own</h2>
      <p className="mt-1 max-w-prose text-sm text-gray-600">
        That's the full app — targets, logging, plans and reports are all yours and need
        nothing else. A household is only worth setting up if you cook with other people and
        want to share recipes and see each other's progress.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="rounded border bg-white p-4">
          <h3 className="font-medium">Start a household</h3>
          <input
            className="mt-2 w-full rounded border p-2"
            placeholder="Household name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button
            className="mt-2 w-full rounded bg-emerald-700 p-2 text-white disabled:opacity-50"
            disabled={!name.trim() || createHousehold.isPending}
            onClick={() => createHousehold.mutate(name.trim())}
          >
            Create household
          </button>
        </div>

        <div className="rounded border bg-white p-4">
          <h3 className="font-medium">Join one you were invited to</h3>
          <input
            className="mt-2 w-full rounded border p-2"
            placeholder="Paste your invite token"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <button
            className="mt-2 w-full rounded border p-2 disabled:opacity-50"
            disabled={!token.trim() || acceptInvite.isPending}
            onClick={() => acceptInvite.mutate(token.trim())}
          >
            Join household
          </button>
          {acceptInvite.isError && (
            <p className="mt-2 text-sm text-red-600">
              That invite is not valid or has expired.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

export function HouseholdScreen() {
  const { data: household, isLoading } = useHousehold()
  const invite = useInvite()
  const leaveHousehold = useLeaveHousehold()
  const updateVisibility = useUpdateVisibility()
  const [email, setEmail] = useState('')

  if (isLoading) return <p className="p-6 text-sm text-gray-600">Loading…</p>
  if (!household) return <NoHousehold />

  const me = household.members[0]

  return (
    <section className="mx-auto max-w-3xl p-6">
      <h2 className="text-xl font-semibold">{household.name}</h2>

      <ul className="mt-4 divide-y rounded border bg-white">
        {household.members.map((member) => (
          <li key={member.user_id} className="flex items-center justify-between p-3">
            <div>
              <p className="font-medium">{member.name}</p>
              <p className="text-sm text-gray-600">{member.email}</p>
            </div>
            <p className="text-sm text-gray-600">
              {member.share_progress ? 'Progress shared' : 'Progress private'}
            </p>
          </li>
        ))}
      </ul>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="font-medium">Invite someone</h3>
          <input
            className="mt-2 w-full rounded border p-2"
            placeholder="their@email.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button
            className="mt-2 w-full rounded border p-2 disabled:opacity-50"
            disabled={!email.trim() || invite.isPending}
            onClick={() => invite.mutate(email.trim())}
          >
            Create invite link
          </button>
          {invite.data && (
            <p className="mt-2 break-all text-sm text-gray-600">
              Share this token with {invite.data.email}: <code>{invite.data.token}</code>
            </p>
          )}
        </div>

        <div>
          <h3 className="font-medium">What you share</h3>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={me?.share_progress ?? true}
              onChange={(event) =>
                updateVisibility.mutate({ share_progress: event.target.checked })
              }
            />
            Share my daily progress with the household
          </label>
          <label className="mt-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={me?.share_health ?? false}
              onChange={(event) =>
                updateVisibility.mutate({ share_health: event.target.checked })
              }
            />
            Share my health details (conditions, weight)
          </label>
        </div>
      </div>

      <div className="mt-8 border-t pt-4">
        <button
          className="rounded border border-red-300 px-3 py-1 text-sm text-red-700 disabled:opacity-50"
          disabled={leaveHousehold.isPending}
          onClick={() => leaveHousehold.mutate()}
        >
          Leave household
        </button>
        <p className="mt-1 text-xs text-gray-500">
          You'll go back to tracking on your own. Your logs, targets and plans stay exactly as
          they are.
        </p>
      </div>
    </section>
  )
}
