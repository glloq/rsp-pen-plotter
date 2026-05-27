/// <reference types="vitest" />
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
  },
  test: {
    // The Playwright suite lives in ``e2e/`` and depends on
    // ``@playwright/test``, which isn't a dev dep until contributors
    // opt in via ``npm run e2e:install``. Excluding the directory
    // from Vitest keeps ``npm test`` deterministic regardless of
    // whether the Playwright runner is on the machine.
    exclude: ['node_modules', 'dist', 'e2e/**'],
  },
})
