import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
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
        // API responses are never precached -- stale nutrient targets would be
        // worse than an honest offline state.
        navigateFallbackDenylist: [/^\/auth/, /^\/households/, /^\/foods/],
      },
    }),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
})
