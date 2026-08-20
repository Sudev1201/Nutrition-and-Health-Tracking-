import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { CycleScreen } from './cycle/CycleScreen'
import { FoodSearchScreen } from './foods/FoodSearchScreen'
import { HouseholdScreen } from './households/HouseholdScreen'
import { LogScreen } from './log/LogScreen'
import { OnboardingWizard } from './onboarding/OnboardingWizard'
import { PlanScreen } from './plan/PlanScreen'
import { RemindersScreen } from './settings/RemindersScreen'
import { AppShell } from './shell/AppShell'
import { MoreScreen } from './shell/MoreScreen'
import { TodayScreen } from './today/TodayScreen'
import { Skeleton } from './ui/feedback'

/*
 * Report and Weight are the only screens that draw charts, and Recharts is by
 * far the heaviest dependency here — bundling it into the entry chunk made every
 * cold start pay for a library most sessions never open. Split out, it is fetched
 * only when a chart is actually asked for, which matters on a phone.
 */
const ReportScreen = lazy(() =>
  import('./report/ReportScreen').then((module) => ({ default: module.ReportScreen })),
)
const WeightScreen = lazy(() =>
  import('./weight/WeightScreen').then((module) => ({ default: module.WeightScreen })),
)

function Deferred({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<Skeleton className="h-96 w-full" />}>{children}</Suspense>
}

export default function App() {
  return (
    <RequireAuth>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<TodayScreen />} />
          <Route path="/log" element={<LogScreen />} />
          <Route path="/plan" element={<PlanScreen />} />
          <Route
            path="/report"
            element={
              <Deferred>
                <ReportScreen />
              </Deferred>
            }
          />
          <Route path="/more" element={<MoreScreen />} />

          <Route
            path="/weight"
            element={
              <Deferred>
                <WeightScreen />
              </Deferred>
            }
          />
          <Route path="/cycle" element={<CycleScreen />} />
          <Route path="/household" element={<HouseholdScreen />} />
          <Route path="/reminders" element={<RemindersScreen />} />
          <Route path="/profile" element={<OnboardingWizard />} />

          <Route path="/foods" element={<FoodSearchScreen />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </RequireAuth>
  )
}
