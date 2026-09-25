import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, test } from 'vitest'
import { apiUrl } from '../mocks/apiUrl'
import { server } from '../mocks/server'
import { AiDescriptionsScreen } from './AiDescriptionsScreen'
import type { LlmSettings } from './types'
import { LLM_SETTINGS_KEY } from './useLlmSettings'

// Obviously fake: the right shape for the form, and useless anywhere else.
const KEY = 'sk-ant-api03-' + 'x'.repeat(40) + 'WXYZ'

const MODELS = ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5']

const NO_KEY: LlmSettings = {
  available: true,
  provider: null,
  model: null,
  key_hint: null,
  status: 'none',
  models: MODELS,
}

function savedWith(model: string): LlmSettings {
  return { ...NO_KEY, provider: 'anthropic', model, key_hint: 'WXYZ', status: 'ok' }
}

beforeEach(() => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(NO_KEY)))
})

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AiDescriptionsScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

/** Paste, as people do with a key, rather than type it. */
async function enterKey(field: HTMLElement) {
  await userEvent.click(field)
  await userEvent.paste(KEY)
}

// --- what the screen says -----------------------------------------------------------------

test('a server with no keyring says so, and asks for no key', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () =>
      HttpResponse.json<LlmSettings>({ ...NO_KEY, available: false }),
    ),
  )
  renderScreen()

  expect(await screen.findByRole('note')).toHaveTextContent(
    'AI descriptions are not set up on this server.',
  )
  expect(screen.getByRole('heading', { name: 'AI descriptions' })).toBeInTheDocument()
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
})

// Removing a key needs no keyring (Task 4), so a key saved before the server lost
// its keyring can always be taken back, whatever its status.
test.each(['ok', 'rejected', 'unreadable'] as const)(
  'a server with no keyring still lets a stored key be removed (%s)',
  async (status) => {
    let current: LlmSettings = { ...savedWith('claude-sonnet-5'), status, available: false }
    let deletes = 0
    server.use(
      http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)),
      http.delete(apiUrl('/settings/llm'), () => {
        deletes += 1
        current = { ...NO_KEY, available: false }
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderScreen()

    expect(await screen.findByRole('note')).toHaveTextContent(
      'AI descriptions are not set up on this server.',
    )
    expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
    expect(screen.getByText('Model: Claude Sonnet 5')).toBeInTheDocument()
    // Nothing on this server can check a key, so there is none to enter.
    expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Replace key' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Remove key' }))

    await waitFor(() => expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument())
    expect(deletes).toBe(1)
    expect(screen.getByRole('note')).toHaveTextContent(
      'AI descriptions are not set up on this server.',
    )
    expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
  },
)

test('says what is sent, who pays, and what happens when Claude Opus 5 declines', async () => {
  renderScreen()

  expect(
    await screen.findByText(
      'Only dish names and ingredient names are sent — never your health details, portions ' +
        'or any numbers. Anthropic bills your account for each request.',
    ),
  ).toBeInTheDocument()
  expect(
    screen.getByText(
      'If Claude Opus 5 declines a request, Anthropic re-runs it on another Claude model and ' +
        "bills that model's rate.",
    ),
  ).toBeInTheDocument()
})

// A key on screen is a key in a screenshot. A browser ignores `autocomplete="off"`
// on a password field; `new-password` is what stops it filling in a saved one.
test('the key field hides what is typed, starts empty, and is marked new-password', async () => {
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  expect(field).toHaveAttribute('type', 'password')
  expect(field).toHaveAttribute('autocomplete', 'new-password')
  expect(field).toHaveValue('')
})

test('offers the server’s models by name, the default first', async () => {
  renderScreen()

  const model = await screen.findByLabelText('Model')
  expect(model).toHaveValue('claude-opus-5')
  expect(
    Array.from(model.querySelectorAll('option'), (option) => option.textContent),
  ).toStrictEqual(['Claude Opus 5', 'Claude Sonnet 5', 'Claude Haiku 4.5'])
})

// --- saving a key -------------------------------------------------------------------------

test('a key goes up with the chosen model, and only its last four come back', async () => {
  let sent: unknown = null
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  server.use(
    http.put(apiUrl('/settings/llm'), async ({ request }) => {
      sent = await request.json()
      await held
      return HttpResponse.json(savedWith('claude-sonnet-5'))
    }),
  )
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  await enterKey(field)
  await userEvent.selectOptions(screen.getByLabelText('Model'), 'claude-sonnet-5')
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  // Emptied as it is sent, not once it is saved.
  expect(field).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
  expect(await screen.findByRole('status')).toHaveTextContent('Checking the key with Anthropic…')
  release()

  expect(await screen.findByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
  expect(screen.getByText('Model: Claude Sonnet 5')).toBeInTheDocument()
  expect(sent).toStrictEqual({ api_key: KEY, model: 'claude-sonnet-5' })
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(document.body.innerHTML.includes(KEY)).toBe(false)
})

test('a saved key shows its last four characters and its model', async () => {
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))))
  renderScreen()

  expect(await screen.findByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
  expect(screen.getByText('Model: Claude Opus 5')).toBeInTheDocument()
  expect(screen.queryByLabelText('Anthropic API key')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open this week’s plan' })).toHaveAttribute(
    'href',
    '/plan',
  )
})

test('a key the server turns down says why, and is not kept in the field', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () =>
      HttpResponse.json({ detail: 'Anthropic refused this key' }, { status: 422 }),
    ),
  )
  renderScreen()

  const field = await screen.findByLabelText('Anthropic API key')
  await enterKey(field)
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/^Anthropic refused this key$/)
  expect(field).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeDisabled()
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
})

// A mutation remembers what it was sent. Once the answer is in, nothing needs the key.
test('the page lets go of the key once the answer is in', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () =>
      HttpResponse.json({ detail: 'Anthropic refused this key' }, { status: 422 }),
    ),
  )
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  await screen.findByRole('alert')
  await waitFor(() => expect(queryClient.getMutationCache().getAll().length).toBe(0))
})

// The common path: a saved key must not linger in the mutation cache either.
test('the page lets go of the key once it is saved, too', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))),
  )
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  await screen.findByText('Key saved: sk-ant-…WXYZ')
  await waitFor(() => expect(queryClient.getMutationCache().getAll().length).toBe(0))
})

// A proxy's error page is not a sentence written for the user, and neither is
// FastAPI's own 422 list; errorDetail's tests cover both.
test('a failure with no sentence to show says so in its own words', async () => {
  server.use(
    http.put(apiUrl('/settings/llm'), () => new HttpResponse('Bad gateway', { status: 502 })),
  )
  renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  await userEvent.click(screen.getByRole('button', { name: 'Save key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The key could not be saved. Please try again.',
  )
})

test.each([
  ['rejected', 'Anthropic refused this key. Enter a new one.'],
  ['unreadable', 'This key can no longer be read on this server. Enter it again.'],
] as const)('asks for the key again when it is %s', async (status, message) => {
  server.use(
    http.get(apiUrl('/settings/llm'), () =>
      HttpResponse.json<LlmSettings>({ ...savedWith('claude-haiku-4-5'), status }),
    ),
  )
  renderScreen()

  expect(await screen.findByText(message)).toBeInTheDocument()
  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
  // The model it was saved with, so entering the key again is all it takes.
  expect(screen.getByLabelText('Model')).toHaveValue('claude-haiku-4-5')
  expect(screen.getByRole('button', { name: 'Save key' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Remove key' })).toBeInTheDocument()
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
})

// --- replacing and removing ---------------------------------------------------------------

test('replacing a key starts from an empty field, and can be called off', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-sonnet-5'))),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Replace key' }))

  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
  expect(screen.getByLabelText('Model')).toHaveValue('claude-sonnet-5')
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
})

// The same, when the form comes back by itself: the key saved from another tab
// has since been refused.
test('a key pasted but not sent is gone when the form comes back by itself', async () => {
  let current = NO_KEY
  server.use(http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)))
  const queryClient = renderScreen()

  await enterKey(await screen.findByLabelText('Anthropic API key'))
  current = savedWith('claude-opus-5')
  await act(() => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }))
  await screen.findByText('Key saved: sk-ant-…WXYZ')
  current = { ...current, status: 'rejected' }
  await act(() => queryClient.invalidateQueries({ queryKey: LLM_SETTINGS_KEY }))

  expect(
    await screen.findByText('Anthropic refused this key. Enter a new one.'),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Anthropic API key')).toHaveValue('')
})

test('removing the key sends a DELETE and goes back to the form', async () => {
  let current = savedWith('claude-opus-5')
  let deletes = 0
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(current)),
    http.delete(apiUrl('/settings/llm'), () => {
      deletes += 1
      current = NO_KEY
      return new HttpResponse(null, { status: 204 })
    }),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove key' }))

  expect(await screen.findByLabelText('Anthropic API key')).toHaveValue('')
  expect(deletes).toBe(1)
  expect(screen.queryByText(/Key saved/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove key' })).not.toBeInTheDocument()
})

test('a key that could not be removed says so, and stays', async () => {
  server.use(
    http.get(apiUrl('/settings/llm'), () => HttpResponse.json(savedWith('claude-opus-5'))),
    http.delete(apiUrl('/settings/llm'), () => new HttpResponse('boom', { status: 500 })),
  )
  renderScreen()

  await userEvent.click(await screen.findByRole('button', { name: 'Remove key' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'The key could not be removed. Please try again.',
  )
  await waitFor(() => expect(screen.getByRole('button', { name: 'Remove key' })).toBeEnabled())
  expect(screen.getByText('Key saved: sk-ant-…WXYZ')).toBeInTheDocument()
})
