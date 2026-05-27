// Playwright config (roadmap G.3 wire — scaffold).
//
// Provides the smallest workable config so `npx playwright test`
// runs the e2e suite against a locally-launched Vite dev server.
// The suite focuses on the modal V2 flow (the v0.2 surface most
// likely to regress as the resolver wires evolve).
//
// Setup:
//   npm install --save-dev @playwright/test
//   npx playwright install --with-deps chromium
//   npm run e2e

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        port: 5173,
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
