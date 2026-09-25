import { NavLink } from 'react-router-dom'
import { cx } from '../lib/cx'
import { MORE_NAV, PRIMARY_NAV } from './navigation'
import type { NavItem } from './navigation'

function SidebarLink({ path, label, icon: Icon, exact }: NavItem) {
  return (
    <li>
      <NavLink
        to={path}
        end={exact}
        className={({ isActive }) =>
          cx(
            'flex min-h-11 items-center gap-3 rounded-control px-3 text-sm',
            isActive ? 'bg-accent-soft font-medium text-accent' : 'text-text-muted hover:bg-surface-alt',
          )
        }
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        {label}
      </NavLink>
    </li>
  )
}

/**
 * The wide-screen navigation. A phone has room for five tabs, so Weight, Cycle,
 * Household, Reminders, AI descriptions and Profile hide behind More there — but
 * a 1440px window has room for all of them, and importing the phone's constraint
 * would be gratuitous. Same `navigation.ts` source, different affordance.
 */
export function Sidebar() {
  return (
    <nav aria-label="Main">
      <ul className="space-y-0.5 p-3">
        {PRIMARY_NAV.map((item) => (
          <SidebarLink key={item.path} {...item} />
        ))}
      </ul>

      <hr className="mx-3 border-border" />

      <ul className="space-y-0.5 p-3">
        {MORE_NAV.map((item) => (
          <SidebarLink key={item.path} {...item} />
        ))}
      </ul>
    </nav>
  )
}
