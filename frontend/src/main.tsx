import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

const queryClient = new QueryClient()

/**
 * Mocks are on in dev by default and off in a production build. Set
 * `VITE_USE_MOCKS=false` to run dev with no worker at all. With no fixture
 * handlers left, the worker serves only opt-in demo auth (`VITE_DEMO_AUTH=true`).
 * The import is dynamic so MSW is tree-shaken out of the production bundle
 * entirely rather than shipped and skipped.
 */
async function startMocks(): Promise<void> {
  const flag = import.meta.env.VITE_USE_MOCKS
  const enabled = flag === undefined ? import.meta.env.DEV : flag === 'true'
  if (!enabled) return

  const { worker } = await import('./mocks/browser')
  await worker.start({
    // Anything without a handler is a real endpoint -- send it to FastAPI.
    onUnhandledRequest: 'bypass',
    serviceWorker: { url: '/mockServiceWorker.js' },
  })
}

startMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
})
