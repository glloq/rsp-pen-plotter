// Effective palette resolution: pens / available / union → ordered hex list.
//
// Lifted out of StyleTab.vue so the resolution rule has a unit test
// independent of Vue / Pinia plumbing. The function is intentionally
// pure: inputs in, hex list out, no reactivity.

import type { PaletteSource } from '../api/client'

/**
 * Resolve the effective palette the per-layer picker should read from.
 *
 * @param source Which pool the operator picked in the Plotter drawer.
 * @param installedPens Colours from the currently-mounted pen slots,
 *   in slot order (so swapping pens doesn't shuffle the palette).
 * @param available Colours from the global available-colours inventory,
 *   ordered by ``position``.
 * @returns The resolved palette. For ``union`` pens come first
 *   (machine reality wins on tie-break) and the inventory's extras
 *   follow, deduplicated case-insensitively against the pens list.
 */
export function resolveEffectivePalette(
  source: PaletteSource,
  installedPens: readonly string[],
  available: readonly string[],
): string[] {
  if (source === 'available') return [...available]
  if (source === 'union') {
    const seen = new Set(installedPens.map((p) => p.toLowerCase()))
    const extras = available.filter((h) => !seen.has(h.toLowerCase()))
    return [...installedPens, ...extras]
  }
  // ``pens`` — default, preserves the legacy behaviour.
  return [...installedPens]
}
