// Locale coverage guard.
//
// Two raw-key leaks reached the UI unnoticed (the layout rail header
// literally rendered "PLANRAIL.TITLE", and the whole PDF block-map card
// showed its key names) because nothing verified that keys referenced in
// templates exist in the locale files. This test walks every non-test
// .vue/.ts source, extracts the STATIC keys passed to ``t('…')`` and
// asserts they resolve in both locales, plus full EN/FR key parity.
//
// Dynamic keys (template literals, computed segments) are out of reach of
// the static regex and stay covered by their own component tests.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import en from './en.json'
import fr from './fr.json'

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

function flattenKeys(node: unknown, prefix = ''): Set<string> {
  const keys = new Set<string>()
  if (node === null || typeof node !== 'object') return keys
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const full = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') {
      for (const sub of flattenKeys(value, full)) keys.add(sub)
    } else {
      keys.add(full)
    }
  }
  return keys
}

function sourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path))
    } else if (/\.(vue|ts)$/.test(entry) && !entry.includes('.test.')) {
      out.push(path)
    }
  }
  return out
}

// Static single-quoted / double-quoted first argument of a bare ``t(…)``
// call. The negative look-behind keeps ``t`` from matching inside longer
// identifiers (``format(``, ``left(``, ``prompt(`` …).
const STATIC_KEY = /(?<![A-Za-z0-9_$.])t\(\s*['"]([A-Za-z0-9_.-]+)['"]/g

function usedStaticKeys(): Set<string> {
  const used = new Set<string>()
  for (const file of sourceFiles(SRC_ROOT)) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(STATIC_KEY)) {
      used.add(match[1]!)
    }
  }
  return used
}

describe('i18n coverage', () => {
  const enKeys = flattenKeys(en)
  const frKeys = flattenKeys(fr)

  it('en and fr define exactly the same keys', () => {
    const onlyEn = [...enKeys].filter((k) => !frKeys.has(k))
    const onlyFr = [...frKeys].filter((k) => !enKeys.has(k))
    expect({ onlyEn, onlyFr }).toEqual({ onlyEn: [], onlyFr: [] })
  })

  it('every static t() key used in src resolves in the locales', () => {
    const missing = [...usedStaticKeys()].filter((k) => !enKeys.has(k)).sort()
    expect(missing).toEqual([])
  })
})
