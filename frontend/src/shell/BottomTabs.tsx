import { NavLink } from 'react-router-dom'
import { cx } from '../lib/cx'
import { TAB_NAV } from './navigation'

/**
 * The phone navigation. Hidden from `md` up, where `Sidebar` takes over.
 *
 * Padded by `env(safe-area-inset-bottom)` so the tabs clear the iPhone home
 * indicator instead of sitting under it.
 */
export function BottomTabs() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-surface md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="flex">
        {TAB_NAV.map(({ path, label, icon: Icon, exact }) => (
          <li key={path} className="flex-1">
            <NavLink
              to={path}
              end={exact}
              className={({ isActive }) =>
                cx(
                  'flex min-h-14 flex-col items-center justify-center gap-1 text-xs',
                  isActive ? 'text-accent' : 'text-text-muted',
                )
              }
            >
              <Icon className="size-5" aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
