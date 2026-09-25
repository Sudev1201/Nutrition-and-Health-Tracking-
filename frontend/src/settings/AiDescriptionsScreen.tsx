import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorDetail } from '../lib/api'
import { Button } from '../ui/Button'
import { Card, CardTitle } from '../ui/Card'
import { Field, Select, TextInput } from '../ui/fields'
import { Skeleton } from '../ui/feedback'
import { MODEL_LABELS } from './types'
import type { LlmKeyStatus, LlmSettings } from './types'
import { useDeleteLlmKey, useLlmSettings, useSaveLlmKey } from './useLlmSettings'

const INTRO =
  'Add a one-line description and a cooking tip to each dish in your plan, written by ' +
  'Claude using your own Anthropic API key.'

const PRIVACY =
  'Only dish names and ingredient names are sent — never your health details, portions ' +
  'or any numbers. Anthropic bills your account for each request.'

// Only Claude Opus 5 is sent with the server-side fallback (backend providers.FALLBACK_MODELS).
const FALLBACK =
  'If Claude Opus 5 declines a request, Anthropic re-runs it on another Claude model and ' +
  "bills that model's rate."

const NOT_AVAILABLE = 'AI descriptions are not set up on this server.'

const STORED_WHILE_OFF =
  'Your key is still stored here, encrypted, but nothing can use it until AI descriptions ' +
  'are set up again. You can remove it.'

/** Why a stored key has to be entered again. */
const NEEDS_NEW_KEY: Partial<Record<LlmKeyStatus, string>> = {
  rejected: 'Anthropic refused this key. Enter a new one.',
  unreadable: 'This key can no longer be read on this server. Enter it again.',
}

const KEY_HINT =
  'It starts with sk-ant-. Anthropic checks it before it is saved. It is stored encrypted, ' +
  'and never shown again.'

const SAVE_FAILED = 'The key could not be saved. Please try again.'
const REMOVE_FAILED = 'The key could not be removed. Please try again.'

function modelLabel(model: string | null): string {
  if (model === null) return ''
  return MODEL_LABELS[model] ?? model
}

/** The stored model while the server still offers it, else the server's default. */
function initialModel(settings: LlmSettings): string {
  if (settings.model !== null && settings.models.includes(settings.model)) return settings.model
  return settings.models[0] ?? ''
}

/** All the server says about a stored key: its last four characters and its model. */
function SavedKey({ settings }: { settings: LlmSettings }) {
  return (
    <>
      <p className="mt-2 text-sm font-medium">
        {`Key saved: sk-ant-…${settings.key_hint ?? ''}`}
      </p>
      <p className="text-sm">{`Model: ${modelLabel(settings.model)}`}</p>
    </>
  )
}

/** What `useDeleteLlmKey()` returns — passed in, never created, by the two pieces below. */
type DeleteLlmKey = ReturnType<typeof useDeleteLlmKey>

/**
 * Just the "Remove key" button, reading the pending state of a mutation its
 * caller owns. No component here calls `useDeleteLlmKey()` itself: `KeyCard` and
 * `StoredKeyCard` swap which view is mounted (the saved view, the form, or the
 * no-keyring note) while staying mounted themselves, so the mutation has to live
 * in them — a shared component that called the hook would be torn down and
 * rebuilt on every such swap, taking any in-flight request's `onSuccess` with it.
 */
function RemoveKeyButton({
  remove,
  disabled = false,
  onClick,
}: {
  remove: DeleteLlmKey
  /** Held off while another request that touches this key is in flight. */
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <Button variant="danger" disabled={remove.isPending || disabled} onClick={onClick}>
      Remove key
    </Button>
  )
}

/** The same mutation's failure message, wherever "Remove key" is offered. */
function RemoveKeyFailed({ remove }: { remove: DeleteLlmKey }) {
  if (!remove.isError) return null
  return (
    <p role="alert" className="mt-2 text-sm text-above-limit">
      {REMOVE_FAILED}
    </p>
  )
}

/**
 * A key saved before this server lost its keyring. Nothing here can check or use
 * it, so there is no form and no "Replace key". But removing a key needs no
 * keyring, so the user can always take theirs back.
 */
function StoredKeyCard({ settings }: { settings: LlmSettings }) {
  const remove = useDeleteLlmKey()

  return (
    <Card>
      <CardTitle>Your Anthropic API key</CardTitle>
      <SavedKey settings={settings} />
      <p className="mt-2 text-sm text-text-muted">{STORED_WHILE_OFF}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <RemoveKeyButton remove={remove} onClick={() => remove.mutate()} />
      </div>
      <RemoveKeyFailed remove={remove} />
    </Card>
  )
}

function KeyCard({ settings }: { settings: LlmSettings }) {
  const save = useSaveLlmKey()
  const remove = useDeleteLlmKey()
  // Never pre-filled, since the server never sends the key back, and emptied the
  // moment it is sent: a typed key stays in this page no longer than the request.
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(() => initialModel(settings))
  const [replacing, setReplacing] = useState(false)
  // Kept here rather than read from `save.error`, because the mutation is reset
  // as soon as it settles: it holds the key it was sent.
  const [saveError, setSaveError] = useState<string | null>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const typed = apiKey.trim()
    if (typed === '') return
    setApiKey('')
    setSaveError(null)
    save.mutate(
      { api_key: typed, model },
      {
        onSuccess: () => setReplacing(false),
        onError: (failure) => setSaveError(errorDetail(failure, SAVE_FAILED)),
        onSettled: () => save.reset(),
      },
    )
  }

  function startReplacing() {
    setApiKey('')
    setSaveError(null)
    setModel(initialModel(settings))
    setReplacing(true)
  }

  function stopReplacing() {
    setApiKey('')
    setSaveError(null)
    setReplacing(false)
  }

  function removeKey() {
    setSaveError(null)
    remove.mutate(undefined, { onSuccess: () => setReplacing(false) })
  }

  const saved = settings.status === 'ok' && !replacing
  // Whatever was pasted and not sent goes whenever the form opens or closes. The
  // handlers above cover a click. This covers the form closing with no click: a
  // refetch that finds a key saved from another tab puts the saved view in its
  // place, and "Replace key", or the key later turning out refused, would
  // otherwise bring the form back still holding the pasted key.
  const formOpen = !saved
  const [formWasOpen, setFormWasOpen] = useState(formOpen)
  if (formOpen !== formWasOpen) {
    setFormWasOpen(formOpen)
    setApiKey('')
  }
  const needsNewKey = NEEDS_NEW_KEY[settings.status]
  // A key Anthropic refused, or one the server cannot read, can still be removed.
  const removeButton = settings.status !== 'none' && (
    <RemoveKeyButton remove={remove} disabled={save.isPending} onClick={removeKey} />
  )

  return (
    <Card>
      <CardTitle>Your Anthropic API key</CardTitle>

      {saved ? (
        <>
          <SavedKey settings={settings} />
          <p className="mt-2 text-sm text-text-muted">
            Anthropic checks the key against the model it is saved with, so to use another model,
            replace the key and pick it. Descriptions are only added when you ask, from the Plan
            screen.
          </p>
          <Link
            to="/plan"
            className="inline-flex min-h-11 items-center text-sm text-accent underline"
          >
            Open this week’s plan
          </Link>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={startReplacing}>Replace key</Button>
            {removeButton}
          </div>
        </>
      ) : (
        <form className="mt-2" onSubmit={submit}>
          {needsNewKey !== undefined && (
            <p className="mb-3 text-sm text-above-limit">{needsNewKey}</p>
          )}
          <Field label="Anthropic API key" hint={KEY_HINT}>
            {(fieldProps) => (
              <TextInput
                {...fieldProps}
                type="password"
                autoComplete="new-password"
                autoCapitalize="off"
                spellCheck={false}
                placeholder="sk-ant-…"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            )}
          </Field>
          <Field label="Model">
            {(fieldProps) => (
              <Select
                {...fieldProps}
                value={model}
                onChange={(event) => setModel(event.target.value)}
              >
                {settings.models.map((option) => (
                  <option key={option} value={option}>
                    {modelLabel(option)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={apiKey.trim() === '' || save.isPending}
            >
              Save key
            </Button>
            {replacing && (
              <Button variant="quiet" disabled={save.isPending} onClick={stopReplacing}>
                Cancel
              </Button>
            )}
            {removeButton}
          </div>
          {save.isPending && (
            <p role="status" className="mt-2 text-sm text-text-muted">
              Checking the key with Anthropic…
            </p>
          )}
        </form>
      )}

      {saveError !== null && (
        <p role="alert" className="mt-2 text-sm text-above-limit">
          {saveError}
        </p>
      )}
      <RemoveKeyFailed remove={remove} />
    </Card>
  )
}

export function AiDescriptionsScreen() {
  const settings = useLlmSettings()

  if (settings.isPending) return <Skeleton className="h-64 w-full" />
  if (settings.isError || settings.data === undefined) {
    return (
      <p role="alert" className="text-sm text-above-limit">
        Your AI description settings could not be loaded. Please try again.
      </p>
    )
  }

  const data = settings.data

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">AI descriptions</h2>
        <p className="mt-1 max-w-prose text-sm text-text-muted">{INTRO}</p>
      </div>

      {data.available ? (
        <>
          <Card>
            <CardTitle>What is sent</CardTitle>
            <p className="mt-1 text-sm">{PRIVACY}</p>
            <p className="mt-2 text-sm text-text-muted">{FALLBACK}</p>
          </Card>
          <KeyCard settings={data} />
        </>
      ) : (
        <>
          <p
            role="note"
            className="rounded-card border border-border bg-surface px-4 py-3 text-sm text-text-muted"
          >
            {NOT_AVAILABLE}
          </p>
          {data.status !== 'none' && <StoredKeyCard settings={data} />}
        </>
      )}
    </section>
  )
}
