import { useState } from 'react'
import {
  useCreateHousehold,
  useHousehold,
  useInvite,
  useUpdateVisibility,
} from './useHousehold'

export function HouseholdScreen() {
  const { data: household, isLoading } = useHousehold()
  const createHousehold = useCreateHousehold()
  const invite = useInvite()
  const updateVisibility = useUpdateVisibility()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')

  if (isLoading) return <p className="p-6 text-sm text-gray-600">Loading…</p>

  if (!household) {
    return (
      <section className="mx-auto max-w-md p-6">
        <h2 className="text-xl font-semibold">Create your household</h2>
        <p className="mt-1 text-sm text-gray-600">
          Household members share the dishes you add, but health details stay private.
        </p>
        <input
          className="mt-4 w-full rounded border p-2"
          placeholder="Household name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button
          className="mt-3 w-full rounded bg-emerald-700 p-2 text-white disabled:opacity-50"
          disabled={!name.trim() || createHousehold.isPending}
          onClick={() => createHousehold.mutate(name.trim())}
        >
          Create household
        </button>
      </section>
    )
  }

  const me = household.members[0]

  return (
    <section className="mx-auto max-w-3xl p-6">
      <h2 className="text-xl font-semibold">{household.name}</h2>

      <ul className="mt-4 divide-y rounded border">
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
    </section>
  )
}
