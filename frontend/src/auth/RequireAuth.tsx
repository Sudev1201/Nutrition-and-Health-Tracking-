import type { ReactNode } from 'react'
import { SignInScreen } from './SignInScreen'
import { useSession } from './useSession'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useSession()

  if (isLoading) return <p className="p-6 text-sm text-gray-600">Loading…</p>
  if (!user) return <SignInScreen />
  return <>{children}</>
}
