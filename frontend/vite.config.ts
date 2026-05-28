import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Vendor + heavy optional surfaces split into separate chunks so the
// initial parse cost on a Pi-class device drops and the browser can
// cache vendor code independently of app code. The ``build`` block
// is typed as ``any`` because vitest's ``defineConfig`` ships a
// rolldown-flavoured ``OutputOptions`` that's incompatible with the
// rollup-flavoured type bundled with vite; the runtime config
// works regardless.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const build: any = {
  rollupOptions: {
    output: {
      manualChunks: {
        'vendor-vue': ['vue', 'pinia', 'vue-i18n'],
        'vendor-zod': ['zod'],
        'vendor-dompurify': ['dompurify'],
        'vendor-axios': ['axios'],
      },
    },
  },
  chunkSizeWarningLimit: 600,
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
  },
  build,
  test: {
    // The Playwright suite lives in ``e2e/`` and depends on
    // ``@playwright/test``, which isn't a dev dep until contributors
    // opt in via ``npm run e2e:install``. Excluding the directory
    // from Vitest keeps ``npm test`` deterministic regardless of
    // whether the Playwright runner is on the machine.
    exclude: ['node_modules', 'dist', 'e2e/**'],
  },
})
