import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { HomeScreen } from './HomeScreen'
import { RequireAuth } from './auth/RequireAuth'
import { HouseholdScreen } from './households/HouseholdScreen'

export default function App() {
  return (
    <RequireAuth>
      <AppShell>
        <Routes>
          <Route path="/" element={<HomeScreen />} />
          <Route path="/household" element={<HouseholdScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </RequireAuth>
  )
}
