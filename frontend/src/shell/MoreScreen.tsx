import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { MORE_NAV } from './navigation'

/**
 * The phone's overflow list. There is no desktop equivalent — the sidebar shows
 * these destinations inline — so a wide viewport that lands here is told where
 * they went rather than shown a redundant list.
 */
export function MoreScreen() {
  return (
    <section>
      <ul className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface md:hidden">
        {MORE_NAV.map(({ path, label, icon: Icon }) => (
          <li key={path}>
            <Link to={path} className="flex min-h-14 items-center gap-3 px-4 text-sm">
              <Icon className="size-4 text-text-muted" aria-hidden="true" />
              {label}
              <ChevronRight className="ml-auto size-4 text-text-muted" aria-hidden="true" />
            </Link>
          </li>
        ))}
      </ul>

      <p className="hidden text-sm text-text-muted md:block">
        These are listed in the sidebar on a screen this wide.
      </p>
    </section>
  )
}
