import type { ReactNode } from 'react'
import { useSession, useSignOut } from './auth/useSession'

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const signOut = useSignOut()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between p-4">
          <span className="font-semibold">Nutrient Tracker</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-gray-600 sm:inline">{user?.email}</span>
            <button className="rounded border px-3 py-1" onClick={() => signOut.mutate()}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl">{children}</main>
      <footer className="mx-auto max-w-5xl p-6 text-xs text-gray-500">
        This app is not medical advice and does not replace a clinician or dietitian.
      </footer>
    </div>
  )
}
