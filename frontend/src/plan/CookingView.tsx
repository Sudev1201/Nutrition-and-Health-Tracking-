import { useHousehold } from '../households/useHousehold'
import { SLOT_LABELS } from '../log/types'
import { Card, CardTitle } from '../ui/Card'
import { Skeleton } from '../ui/feedback'
import { useCookingView } from './usePlan'

/**
 * Where household members' plans coincide on one day, so a dish can be cooked
 * once and portioned per person. Solo users never see it: there is nothing to
 * reconcile, and the spec is explicit that solo is the complete experience.
 */
export function CookingView({ date, weekday }: { date: string; weekday: string }) {
  const household = useHousehold()
  const inHousehold = household.data != null
  const cooking = useCookingView(date, inHousehold)

  if (!inHousehold) return null

  return (
    <section aria-labelledby="cooking-together" className="mb-4">
      <Card>
        <CardTitle>
          <span id="cooking-together">Cooking together</span>
        </CardTitle>
        {cooking.isPending && <Skeleton className="mt-2 h-10 w-full" />}
        {cooking.isError && (
          <p role="alert" className="mt-2 text-sm text-above-limit">
            The cooking view could not be loaded.
          </p>
        )}
        {cooking.data !== undefined && cooking.data.overlaps.length === 0 && (
          <p className="mt-2 text-sm text-text-muted">
            No two plans share a dish on {weekday}.
          </p>
        )}
        {cooking.data !== undefined && cooking.data.overlaps.length > 0 && (
          <ul className="mt-2 divide-y divide-border">
            {cooking.data.overlaps.map((overlap) => (
              <li key={`${overlap.slot}-${overlap.dish_name}`} className="py-2">
                <span className="text-xs text-text-muted">{SLOT_LABELS[overlap.slot]}</span>
                <p className="text-sm font-medium">{overlap.dish_name}</p>
                <p className="text-xs text-text-muted">{overlap.members.join(', ')}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  )
}
