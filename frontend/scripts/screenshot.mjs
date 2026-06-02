// Screenshot harness for the OmniPlot UI. Drives a real headless chromium
// against the running backend + built frontend on http://127.0.0.1:8765.
//
// Output: docs/images/screenshot-*.png

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const BASE = 'http://127.0.0.1:8765'
const OUT  = resolve(process.cwd(), '..', 'docs', 'images')
mkdirSync(OUT, { recursive: true })

const VIEW = { width: 1440, height: 900 }
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const ctx = await browser.newContext({
  viewport: VIEW,
  deviceScaleFactor: 2,
  locale: 'fr-FR',
})
const page = await ctx.newPage()

page.on('console', (msg) => {
  if (msg.type() === 'error') console.error('  [browser err]', msg.text())
})

async function shot(name, opts = {}) {
  const out = `${OUT}/screenshot-${name}.png`
  await page.screenshot({ path: out, fullPage: false, ...opts })
  console.log(`  saved ${out}`)
}

console.log('[1] main interface')
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('text=FICHIERS', { timeout: 15000 }).catch(() => {})
await page.waitForTimeout(1500)
await shot('main-interface')

// 2) Place the city map on the sheet then click Edit (pencil) to open the editor.
//    We can't drag from the file row reliably in headless, so we call the
//    edit handler by clicking the pencil button on the row.
console.log('[2] editor')
const cityRow = page.locator('li:has-text("city-map.svg")').first()
if (await cityRow.count()) {
  // The pencil "✎" is the edit button. Click it.
  const edit = cityRow.locator('button[title*="églages" i], button[title*="conversion" i]').first()
  if (await edit.count()) {
    await edit.click().catch(() => {})
  } else {
    // Fallback: double-click the row, which also triggers edit.
    await cityRow.dblclick().catch(() => {})
  }
  await page.waitForTimeout(1800)
  await shot('editor')
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(500)
}

// 3) Settings drawer
console.log('[3] settings drawer')
const settingsBtn = page.locator('button[aria-label="Réglages"]').first()
if (await settingsBtn.count()) {
  await settingsBtn.click().catch(() => {})
  await page.waitForTimeout(800)
  await shot('settings-drawer')
  await page.keyboard.press('Escape').catch(() => {})
  await page.waitForTimeout(400)
}

// 4) Plotter tab
console.log('[4] plotter tab')
const plotterTab = page.locator('[data-test="canvas-tab-plotter"]').first()
if (await plotterTab.count()) {
  await plotterTab.click().catch(() => {})
  await page.waitForTimeout(800)
  await shot('plotter-tab')
}

// 5) Files pane close-up — just the left column, sheet stays empty
console.log('[5] files pane close-up')
const sheetTab = page.locator('[data-test="canvas-tab-sheet"]').first()
if (await sheetTab.count()) {
  await sheetTab.click().catch(() => {})
  await page.waitForTimeout(400)
}
await shot('files-pane', { clip: { x: 0, y: 0, width: 320, height: 900 } })

await browser.close()
console.log('done.')
