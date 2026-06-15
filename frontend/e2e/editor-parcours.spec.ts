// Editor parcours — real browser E2E (audit Phase 3).
//
// Drives the headline editor flow end-to-end in a real browser: upload a
// file, open the V2 editor, wait for the live preview, change the intent
// and palette, switch to expert mode and back, and generate. This is the
// browser-level complement to the component-integration coverage in
// ``src/components/v2/EditModalV2.test.ts`` (which exercises the same
// scenarios against mounted Vue + Pinia, but not the real network wiring).
//
// REQUIREMENTS / HOW TO RUN
//   The flow needs the FastAPI backend up (upload → segmentation → render
//   are real round-trips) AND a Playwright browser installed. It is gated
//   on ``E2E_BACKEND_RUNNING=1`` exactly like ``operator-parcours.spec.ts``
//   so the default Vite-only suite skips it instead of failing:
//
//     npx playwright install --with-deps chromium
//     OMNIPLOT_FAKE_HARDWARE=1 <start backend on :8000>
//     E2E_BACKEND_RUNNING=1 npm run e2e
//
//   NOTE: this spec was authored against the app's data-test hooks and the
//   real API contract but has NOT been executed in CI yet (the authoring
//   environment had no Playwright browser egress). Validate it once in a
//   browser+backend environment before relying on it as a gate.

import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

const backendUp = process.env.E2E_BACKEND_RUNNING === '1'
const FIXTURE = fileURLToPath(new URL('./fixtures/checker.png', import.meta.url))

test.describe('Editor parcours (assisted → expert → generate)', () => {
  test.skip(!backendUp, 'requires E2E_BACKEND_RUNNING=1 with the backend on :8000')

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('[data-test="header-version-badge"]')).toBeVisible()
  })

  async function uploadAndOpenEditor(page: import('@playwright/test').Page) {
    // The file <input> is hidden; set files on it directly rather than
    // clicking the button that proxies to it.
    await page.locator('input[type="file"]').setInputFiles(FIXTURE)
    // The uploaded file lands as a row in the Files pane once the backend
    // finishes segmentation.
    const row = page.locator('[data-test="file-row"]').first()
    await expect(row).toBeVisible({ timeout: 20_000 })
    // Open the editor on it.
    await row.locator('[data-test="file-row-edit"]').click()
    await expect(page.locator('[data-test="modal-v2-layout"]')).toBeVisible({ timeout: 20_000 })
  }

  test('assisted parcours: preview, change intent + palette, then Generate', async ({ page }) => {
    await uploadAndOpenEditor(page)

    // The live preview SVG appears once the first resolve+render lands.
    await expect(page.locator('[data-test="modal-v2-preview-svg"]')).toBeVisible({
      timeout: 20_000,
    })

    // Generate is enabled once the pipeline reaches its terminal state.
    const generate = page.locator('[data-test="confirm-button"]')
    await expect(generate).toBeEnabled({ timeout: 20_000 })

    // Switch the intent — Generate locks while the pipeline re-resolves,
    // then unlocks again.
    await page.locator('[data-test="intent-fast"]').click()
    await expect(page.locator('[data-test="intent-fast"]')).toHaveClass(/active/)
    await expect(generate).toBeEnabled({ timeout: 20_000 })

    // Switch the palette.
    await page.locator('[data-test="palette-free"]').click()
    await expect(page.locator('[data-test="palette-free"]')).toHaveClass(/active/)
    await expect(generate).toBeEnabled({ timeout: 20_000 })

    // Generate closes the modal (the parent commits + tears it down).
    await generate.click()
    await expect(page.locator('[data-test="modal-v2-layout"]')).toBeHidden({ timeout: 20_000 })
  })

  test('expert parcours: switch to expert, see tabs, apply, generate', async ({ page }) => {
    await uploadAndOpenEditor(page)
    await expect(page.locator('[data-test="modal-v2-preview-svg"]')).toBeVisible({
      timeout: 20_000,
    })

    // Flip to the expert surface from the modal header's mode toggle.
    // Scoped to the modal backdrop so it doesn't also match the
    // app-header toggle, which renders the same data-test ids.
    await page
      .locator('[data-test="modal-v2-backdrop"] [data-test="assistant-mode-expert"]')
      .click()
    await expect(page.locator('[data-test="modal-v2-expert-panel"]')).toBeVisible()
    // The lazy-loaded tab strip resolves.
    await expect(page.locator('[role="tablist"]')).toBeVisible({ timeout: 20_000 })

    // Generate remains available from expert mode.
    await expect(page.locator('[data-test="confirm-button"]')).toBeEnabled({ timeout: 20_000 })
    await page.locator('[data-test="confirm-button"]').click()
    await expect(page.locator('[data-test="modal-v2-layout"]')).toBeHidden({ timeout: 20_000 })
  })

  test('Escape closes the editor when there is nothing unsaved', async ({ page }) => {
    await uploadAndOpenEditor(page)
    await page.keyboard.press('Escape')
    await expect(page.locator('[data-test="modal-v2-layout"]')).toBeHidden({ timeout: 10_000 })
  })
})
