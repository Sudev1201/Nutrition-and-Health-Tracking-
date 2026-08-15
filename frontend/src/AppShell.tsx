import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useSession, useSignOut } from './auth/useSession'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-3 py-1 text-sm ${isActive ? 'bg-gray-200 font-medium' : 'text-gray-600'}`

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const signOut = useSignOut()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 p-4">
          <span className="font-semibold">Nutrient Tracker</span>

          <nav className="flex items-center gap-1">
            <NavLink to="/" className={linkClass} end>
              Home
            </NavLink>
            <NavLink to="/household" className={linkClass}>
              Household
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-3 text-sm">
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
