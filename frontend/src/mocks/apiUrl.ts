/**
 * Handlers must match the same absolute origin `src/lib/api.ts` builds its
 * requests against, or MSW silently passes them through to the network.
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
