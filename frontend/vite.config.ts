import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

/*
 * `src/lib/api.ts` falls back to http://localhost:8000 when VITE_API_BASE is unset.
 * That is right for `npm run dev` and wrong for anything deployed: the bundle would
 * send every request to the visitor's own machine, and the build would not say so.
 * So a production build stops instead.
 *
 * - It mirrors the `??` in api.ts: only a missing variable falls back to localhost,
 *   so only a missing variable is refused. `??` keeps an empty one, and so does this.
 * - A mock build (`VITE_USE_MOCKS=true`) is exempt. Its MSW worker holds only the
 *   opt-in demo-auth handlers (`VITE_DEMO_AUTH=true`), so it is a local demo of the
 *   sign-in alone. Every other request still goes to VITE_API_BASE, or to localhost
 *   when that is unset. Such a build is never deployed.
 * - It checks `vite build` only. `vite preview` loads this file in production mode
 *   too, but it serves a finished build and bakes nothing in. Vitest runs in mode
 *   "test" and `vite` in "development", so neither reaches it.
 */
const API_BASE_MISSING =
  'VITE_API_BASE is not set. A production build would call http://localhost:8000. ' +
  'Set it (for example in frontend/.env.local) or set VITE_USE_MOCKS=true.'

function refuseLocalhostBuild(command: 'build' | 'serve', mode: string): void {
  if (command !== 'build' || mode !== 'production') return
  // What Vite itself puts in import.meta.env: .env, .env.local, .env.production and
  // .env.production.local from its root (the working directory, since this config
  // sets none), with the shell's environment winning over all four.
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  if (env.VITE_API_BASE === undefined && env.VITE_USE_MOCKS !== 'true') {
    throw new Error(API_BASE_MISSING)
  }
}

export default defineConfig(({ command, mode }) => {
  refuseLocalhostBuild(command, mode)
  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['apple-touch-icon.png'],
        /*
         * Deliberately off in dev. MSW's worker and this one both claim the root
         * scope, and only one service worker can control a page -- so the mocks own
         * dev, and the PWA worker owns the production build.
         */
        devOptions: { enabled: false },
        manifest: {
          name: 'Nutrient Tracker',
          short_name: 'Nutrients',
          description:
            'Track macros and micronutrients on a South Indian diet, against ICMR-NIN targets.',
          start_url: '/',
          display: 'standalone',
          orientation: 'portrait',
          background_color: '#ffffff',
          theme_color: '#0f766e',
          icons: [
            { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
            {
              src: '/icon-maskable-512.png',
              sizes: '512x512',
              type: 'image/png',
              // Android crops icons to the launcher's shape; the maskable variant
              // keeps its glyph inside the centre 80% so nothing important is cut.
              purpose: 'maskable',
            },
          ],
        },
        workbox: {
          // The app shell is precached so a cold, offline launch still renders.
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          // Vite copies all of public/ into dist, which sweeps up MSW's dev worker.
          // It is never registered in production, but precaching it would ship and
          // cache 8KB of dev tooling to every user.
          globIgnores: ['mockServiceWorker.js'],
          // No navigateFallbackDenylist. The API has its own origin (api.<domain>),
          // so this worker never sees a navigation to it, and every navigation it
          // does see is an SPA route that index.html answers. The old list (/auth,
          // /households, /foods) caught the real /foods screen, so an offline reload
          // there failed. API responses are still never precached: globPatterns
          // matches only this build's own files.
          //
          // The meal reminders' push and notification-click handlers: plain JS in
          // public/, loaded into the generated worker, which stays generateSW. The
          // file is precached too, so an edit to it changes sw.js and updates the
          // worker.
          importScripts: ['push-handlers.js'],
        },
      }),
    ],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.ts',
      /*
       * The Playwright specs live in e2e/ and drive a real browser against a real
       * backend. Vitest's default glob would otherwise collect them and run them
       * under jsdom, where `@playwright/test` has no runner to attach to.
       */
      exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
    },
  }
})
