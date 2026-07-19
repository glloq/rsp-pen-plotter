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

  test('header does NOT carry the mode toggle (moved into the editor)', async ({ page }) => {
    // UX audit Lot 1 (2026-07-19): the assisted/expert selector lives
    // only in the editor's own header now — a global header toggle
    // changed the behaviour of a modal the operator wasn't looking at.
    // Pin the removal so it doesn't quietly come back.
    await expect(page.locator('[data-test="header-version-badge"]')).toBeVisible()
    await expect(page.locator('[data-test="header-assistant-mode-toggle"]')).toHaveCount(0)
  })

  test('perf overlay stays hidden without ?flag.perf=1', async ({ page }) => {
    await expect(page.locator('[data-test="perf-overlay"]')).toHaveCount(0)
  })

  test('perf overlay becomes visible with ?flag.perf=1', async ({ page }) => {
    await page.goto('/?flag.perf=1')
    await expect(page.locator('[data-test="perf-overlay"]')).toBeVisible()
  })
})
