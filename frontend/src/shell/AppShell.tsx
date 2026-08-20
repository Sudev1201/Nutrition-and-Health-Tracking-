import { Outlet } from 'react-router-dom'
import { useSession, useSignOut } from '../auth/useSession'
import { Button } from '../ui/Button'
import { BottomTabs } from './BottomTabs'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

function AccountBlock() {
  const { user } = useSession()
  const signOut = useSignOut()

  return (
    <div className="mt-auto border-t border-border p-3">
      <p className="truncate text-xs text-text-muted" title={user?.email}>
        {user?.email}
      </p>
      <Button variant="quiet" className="mt-1 px-0" onClick={() => signOut.mutate()}>
        Sign out
      </Button>
    </div>
  )
}

/**
 * The application frame. A phone app below `md` — sticky header, scrolling
 * content, fixed tab bar — and a sidebar dashboard from `md` up.
 *
 * The switch is pure CSS rather than a `useMediaQuery` branch, so there is no
 * layout flash on first paint and no second render on resize. Screens then use
 * ordinary responsive classes to go multi-column, which is what keeps the desktop
 * view from being a stretched phone view.
 */
export function AppShell() {
  return (
    <div className="min-h-screen md:flex">
      <div className="hidden md:flex md:min-h-screen md:w-56 md:shrink-0 md:flex-col md:border-r md:border-border md:bg-surface">
        <p className="px-3 py-4 font-semibold">Nutrient Tracker</p>
        <Sidebar />
        <AccountBlock />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />

        {/*
          The tab bar is fixed, so the last card of a long list would sit under it
          without this padding. 4rem covers the 56px bar; the inset covers the home
          indicator below it.
        */}
        <main
          className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-6"
          style={{ paddingBottom: 'calc(4rem + env(safe-area-inset-bottom))' }}
        >
          <Outlet />
        </main>

        <footer className="mx-auto w-full max-w-6xl px-4 pb-24 text-xs text-text-muted md:px-6 md:pb-6">
          This app is not medical advice and does not replace a clinician or dietitian.
        </footer>

        <BottomTabs />
      </div>
    </div>
  )
}
