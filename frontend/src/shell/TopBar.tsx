import { useLocation } from 'react-router-dom'
import { MORE_NAV, MORE_TAB, PRIMARY_NAV } from './navigation'

const ALL_DESTINATIONS = [...PRIMARY_NAV, MORE_TAB, ...MORE_NAV]

function titleFor(pathname: string): string {
  const exact = ALL_DESTINATIONS.find((item) => item.path === pathname)
  if (exact !== undefined) return exact.label

  // Nested routes such as /plan/2026-08-17 keep their section's title.
  const section = ALL_DESTINATIONS.filter((item) => item.path !== '/').find((item) =>
    pathname.startsWith(`${item.path}/`),
  )
  return section?.label ?? 'Nutrient Tracker'
}

/** The phone header. Hidden from `md` up, where the sidebar carries the identity. */
export function TopBar() {
  const { pathname } = useLocation()
  const today = new Date().toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })

  return (
    <header
      className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface px-4 py-3 md:hidden"
      style={{ paddingTop: 'calc(0.75rem + env(safe-area-inset-top))' }}
    >
      <h1 className="text-base font-semibold">{titleFor(pathname)}</h1>
      <span className="text-sm text-text-muted">{today}</span>
    </header>
  )
}
