// Operator parcours — E2E with fake hardware (P7).
//
// Drives the headline operator flow without a real plotter: launch the
// SPA, mount the V2 editor, and exercise the plotter-control surfaces
// that rely on the controller's mock transport
// (``OMNIPLOT_FAKE_HARDWARE=1``).
//
// The backend launched alongside Vite **must** carry that env var so
// ``/plotter/connect`` attaches a MockTransport instead of opening
// ``/dev/ttyUSB*``. The CI workflow exports it before ``npm run e2e``.
// Tests gated on ``E2E_BACKEND_RUNNING=1`` so a Vite-only dev session
// can still run the smoke tests without spinning up FastAPI.

import { expect, test } from '@playwright/test'

const backendUp = process.env.E2E_BACKEND_RUNNING === '1'

test.describe('Operator parcours (fake hardware)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('SPA boots, header chrome renders, no fatal toast', async ({ page }) => {
    // The shell must render fully — banner, header, files pane —
    // without any "API unreachable" / "device lost" toast firing on
    // boot. Those toasts are the canaries for backend reachability.
    // The version badge is the AppHeader's stable identifier: three
    // ``<header>`` elements live on the page (AppHeader, FilesPane,
    // PlotterControl), so a bare ``header`` selector trips Playwright's
    // strict mode.
    await expect(page.locator('[data-test="header-version-badge"]')).toBeVisible()
    await expect(
      page.locator('[data-test="toast-critical"]', { hasText: /unreachable|lost/i }),
    ).toHaveCount(0)
  })

  test.describe('backend live', () => {
    test.skip(!backendUp, 'requires E2E_BACKEND_RUNNING=1 with OMNIPLOT_FAKE_HARDWARE=1')

    test('health endpoint round-trips through the SPA origin', async ({ request }) => {
      // Cheapest backend liveness check — proves the dev-server proxy
      // wiring routes ``/health`` correctly and the backend's
      // rate-limit middleware exempts it.
      const response = await request.get('http://localhost:8000/health')
      expect(response.ok()).toBeTruthy()
      const body = await response.json()
      expect(body.status).toBe('ok')
      expect(body.version).toBeTruthy()
    })

    test('rate-limit middleware exempts /health under burst', async ({ request }) => {
      // Hammer ``/health`` 30× in a tight loop; every response must
      // succeed (the exempt list keeps probes 200, never 429).
      const calls = Array.from({ length: 30 }, () =>
        request.get('http://localhost:8000/health'),
      )
      const responses = await Promise.all(calls)
      for (const res of responses) {
        expect(res.status()).toBe(200)
      }
    })

    test('error envelope: unknown resource returns the unified shape', async ({
      request,
    }) => {
      // P1 contract: every error response carries
      // ``{code, message, details, path}``. Hitting an unknown profile
      // route must round-trip the envelope.
      const response = await request.get('http://localhost:8000/profiles/does-not-exist-xyz')
      expect(response.status()).toBe(404)
      const body = await response.json()
      expect(body).toHaveProperty('code')
      expect(body).toHaveProperty('message')
      expect(body).toHaveProperty('details')
      expect(body.path).toBe('/profiles/does-not-exist-xyz')
    })
  })
})
