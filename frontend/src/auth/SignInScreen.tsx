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

export function SignInScreen() {
  const buttonRef = useRef<HTMLDivElement>(null)
  const signIn = useSignIn()

  useEffect(() => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => {
      if (!window.google || !buttonRef.current) return
      window.google.accounts.id.initialize({
        client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
        callback: (response) => signIn.mutate(response.credential),
      })
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
      })
    }
    document.body.appendChild(script)
    return () => {
      script.remove()
    }
  }, [signIn])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-semibold">Nutrient Tracker</h1>
        <p className="mt-2 text-sm text-gray-600">
          Track macros and micronutrients on a South Indian diet.
        </p>
      </div>
      <div ref={buttonRef} />
      {signIn.isError && (
        <p className="text-sm text-red-600">Sign-in failed. Please try again.</p>
      )}
    </main>
  )
}
