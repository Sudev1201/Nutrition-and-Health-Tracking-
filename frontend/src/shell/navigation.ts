import {
  CalendarDays,
  ClipboardList,
  Droplet,
  Ellipsis,
  Home,
  LineChart,
  PlusCircle,
  Scale,
  Settings,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  /** `/` is a prefix of every route, so Today must match exactly. */
  exact?: boolean
}

/**
 * The single source of truth for navigation. `BottomTabs` and `Sidebar` both read
 * these arrays, so the phone and desktop layouts cannot drift apart as screens are
 * added — which is the failure mode when each layout keeps its own list.
 */
export const PRIMARY_NAV: readonly NavItem[] = [
  { path: '/', label: 'Today', icon: Home, exact: true },
  { path: '/log', label: 'Log', icon: PlusCircle },
  { path: '/plan', label: 'Plan', icon: CalendarDays },
  { path: '/report', label: 'Report', icon: LineChart },
]

/**
 * Reachable behind the More tab on a phone, listed inline in the sidebar on a wide
 * screen where there is room for them.
 */
export const MORE_NAV: readonly NavItem[] = [
  { path: '/weight', label: 'Weight', icon: Scale },
  { path: '/cycle', label: 'Cycle', icon: Droplet },
  { path: '/household', label: 'Household', icon: Users },
  { path: '/reminders', label: 'Reminders', icon: ClipboardList },
  { path: '/profile', label: 'Profile', icon: Settings },
]

export const MORE_TAB: NavItem = { path: '/more', label: 'More', icon: Ellipsis }

/** What the phone tab bar shows: the four primary destinations plus More. */
export const TAB_NAV: readonly NavItem[] = [...PRIMARY_NAV, MORE_TAB]
