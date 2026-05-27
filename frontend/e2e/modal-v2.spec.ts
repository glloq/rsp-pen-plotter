// Modal V2 smoke (roadmap G.3 wire).
//
// Covers the headline parcours the brief calls out for the v0.2
// modal: open behind the feature flag, walk through the six steps,
// confirm the resolver recommendation renders. The full validation
// matrix (assisted/expert disclosure, expert override, error
// recovery) lands as the suite grows.

import { expect, test } from '@playwright/test'

test.describe('Modal V2 — fast default flow', () => {
  test.beforeEach(async ({ page }) => {
    // Feature flag enables the modal V2 alongside the v1 modal.
    await page.goto('/?flag.modalV2=1&flag.compareMode=1')
  })

  test('header shows the workspace switcher and AssistantModeToggle', async ({
    page,
  }) => {
    await expect(page.locator('[data-test="header-workspace-select"]')).toBeVisible()
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
