import { Link } from 'react-router-dom'
import { useSession } from './auth/useSession'

export function HomeScreen() {
  const { user } = useSession()
  const firstName = user?.name?.split(' ')[0] ?? 'there'

  return (
    <section className="p-6">
      <h2 className="text-xl font-semibold">Hello, {firstName}</h2>
      <p className="mt-1 max-w-prose text-sm text-gray-600">
        Your daily dashboard will live here — today's nutrient targets, what you have eaten,
        and anything carried forward from the last two days.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <article className="rounded border bg-white p-4">
          <h3 className="font-medium">Coming next</h3>
          <ul className="mt-2 list-inside list-disc text-sm text-gray-600">
            <li>Your profile and personalised targets</li>
            <li>Logging meals by dish, with household measures</li>
            <li>A weekly South Indian meal plan you can adjust</li>
          </ul>
        </article>

        <article className="rounded border bg-white p-4">
          <h3 className="font-medium">Cooking for others?</h3>
          <p className="mt-2 text-sm text-gray-600">
            Tracking on your own works fully as it is. If you cook with family, a household
            lets you share recipes and see each other's progress.
          </p>
          <Link
            className="mt-3 inline-block rounded border px-3 py-1 text-sm"
            to="/household"
          >
            Set up a household
          </Link>
        </article>
      </div>
    </section>
  )
}
