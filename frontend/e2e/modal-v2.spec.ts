// Modal V2 smoke (roadmap G.3 wire).
//
// Covers the headline parcours the brief calls out for the v0.2
// modal. The V1 editor was removed in the v0.2 migration so the
// ``?flag.modalV2`` query string no longer affects rendering — V2 is
// the only editor. The flag is still set to keep the test URL
// self-documenting in case the route boots a different default in
// the future.

import { expect, test } from '@playwright/test'

test.describe('Modal V2 — fast default flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/?flag.modalV2=1&flag.compareMode=1')
  })

  test('header shows the AssistantModeToggle', async ({ page }) => {
    // The ``header-workspace-select`` data-test attribute the previous
    // scaffold pointed at never existed in the app. The
    // AssistantModeToggle is the real header surface that's been
    // stable since the v0.2 migration.
    await expect(page.locator('[data-test="header-assistant-mode-toggle"]')).toBeVisible()
  })

  test('perf overlay stays hidden without ?flag.perf=1', async ({ page }) => {
    await expect(page.locator('[data-test="perf-overlay"]')).toHaveCount(0)
  })

  test('perf overlay becomes visible with ?flag.perf=1', async ({ page }) => {
    await page.goto('/?flag.perf=1')
    await expect(page.locator('[data-test="perf-overlay"]')).toBeVisible()
  })
})
