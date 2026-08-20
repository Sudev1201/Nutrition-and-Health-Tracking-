import { useEffect, useRef } from 'react'
import { useSignIn } from './useSession'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
          }) => void
          renderButton: (parent: HTMLElement, options: Record<string, string>) => void
        }
      }
    }
  }
}

const GSI_SRC = 'https://accounts.google.com/gsi/client'

export function SignInScreen() {
  const buttonRef = useRef<HTMLDivElement>(null)
  const signIn = useSignIn()

  // `signIn.mutate` is stable across renders; the mutation object around it is
  // not. Depending on the object re-ran this effect on every render, which
  // appended another Google script and called initialize again each time —
  // Google logs "initialize() is called multiple times" and keeps only the last.
  const { mutate } = signIn

  // The callback below is registered with Google once per page, so it must not
  // capture a particular render's `mutate`. A ref keeps it pointing at the
  // current one without re-registering.
  const mutateRef = useRef(mutate)
  useEffect(() => {
    mutateRef.current = mutate
  }, [mutate])

  useEffect(() => {
    function setUpButton(script: HTMLScriptElement) {
      if (!window.google || !buttonRef.current) return

      /*
       * `google.accounts.id` is a page-level singleton: initialising it twice
       * makes Google discard the first instance and warn about it. StrictMode
       * double-invokes this effect in dev, so the "already initialised" fact is
       * recorded on the script element — the same page-scoped object whose
       * presence is already being checked. Module-level state would work too,
       * but would then need a test-only reset hook.
       */
      if (script.dataset.initialised !== 'true') {
        window.google.accounts.id.initialize({
          client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
          callback: (response) => mutateRef.current(response.credential),
        })
        script.dataset.initialised = 'true'
      }

      // Re-rendered on every mount, because the container div is new each time.
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
      })
    }

    // The script is left in place on unmount rather than removed. Google's
    // client is not designed to be torn down and re-added, and removing it made
    // every remount load a second copy.
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`)
    if (existing !== null) {
      if (window.google) setUpButton(existing)
      else existing.addEventListener('load', () => setUpButton(existing), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = GSI_SRC
    script.async = true
    script.addEventListener('load', () => setUpButton(script), { once: true })
    document.body.appendChild(script)
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-semibold">Nutrient Tracker</h1>
        <p className="mt-2 text-sm text-text-muted">
          Track macros and micronutrients on a South Indian diet, against ICMR-NIN targets.
        </p>
      </div>

      <div ref={buttonRef} />

      {signIn.isError && (
        <p role="alert" className="text-sm text-above-limit">
          Sign-in failed. Please try again.
        </p>
      )}

      <p className="max-w-sm text-center text-xs text-text-muted">
        This app is not medical advice and does not replace a clinician or dietitian.
      </p>
    </main>
  )
}
