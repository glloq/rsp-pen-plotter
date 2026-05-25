import { describe, expect, it } from 'vitest'
import {
  ALGORITHMS,
  DEFAULT_MASTER_STYLE_ID,
  LEGACY_MASTER_ID_MAP,
  PRINT_STYLES,
  defaultsFor,
  getAlgorithm,
  layerStyles,
  masterStyles,
  resolveMasterStyle,
} from './printRegistry'

// The registry is the single source of truth for all "style" and
// "algorithm" data the editor uses. These tests pin down the shape
// invariants the UI relies on (no duplicate ids, every master style
// has a usable segmentation, every layer style targets a real
// algorithm) so a future edit to the registry can't silently break
// downstream consumers.

describe('printRegistry', () => {
  it('has unique style ids', () => {
    const ids = PRINT_STYLES.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('partitions cleanly into master + layer styles', () => {
    const total = PRINT_STYLES.length
    const masters = masterStyles().length
    const layers = layerStyles().length
    expect(masters + layers).toBe(total)
    expect(masters).toBeGreaterThan(0)
    expect(layers).toBeGreaterThan(0)
  })

  it('every master style carries a usable segmentation block', () => {
    for (const s of masterStyles()) {
      expect(s.segmentation, `style ${s.id} missing segmentation`).toBeDefined()
      const seg = s.segmentation!
      expect(['luminance_bands', 'thresholds', 'kmeans', 'fixed_palette']).toContain(seg.method)
      // Knob slider is only sensible for band-based segmentations.
      if (seg.method === 'luminance_bands') {
        expect(seg.default_num_bands).toBeGreaterThanOrEqual(2)
      }
      if (seg.method === 'thresholds') {
        expect(seg.default_threshold).toBeGreaterThan(0)
        expect(seg.default_threshold).toBeLessThan(1)
      }
    }
  })

  it('every style targets an algorithm that exists in ALGORITHMS', () => {
    for (const s of PRINT_STYLES) {
      expect(
        getAlgorithm(s.defaultAlgorithm),
        `unknown algo ${s.defaultAlgorithm} in style ${s.id}`,
      ).not.toBeNull()
    }
  })

  it('master shaded band recipes produce valid algorithms for each band', () => {
    for (const s of masterStyles()) {
      if (!s.bandRecipe) continue
      // Exercise the recipe over a handful of band counts including the
      // edge cases (1 band -> recipe should still return something
      // usable; many bands -> indices wrap cleanly).
      for (const total of [1, 2, 4, 8]) {
        for (let i = 0; i < total; i++) {
          const recipe = s.bandRecipe(i, total)
          expect(recipe, `style ${s.id} returned null for band ${i}/${total}`).not.toBeNull()
          expect(getAlgorithm(recipe!.algorithm)).not.toBeNull()
        }
      }
    }
  })

  it('defaultsFor returns a fresh copy each call', () => {
    const a = defaultsFor('halftone')
    const b = defaultsFor('halftone')
    a.cell_size_px = 999
    expect(b.cell_size_px).not.toBe(999)
  })

  it('resolveMasterStyle handles legacy ids, unknown ids, and nullish input', () => {
    // Legacy id (was the only id pre-refactor) maps to the renamed entry.
    expect(resolveMasterStyle('halftone').id).toBe('halftone-shade')
    // Modern id resolves directly.
    expect(resolveMasterStyle('pencil').id).toBe('pencil')
    // Unknown id falls back to the default master.
    expect(resolveMasterStyle('definitely-not-a-style').id).toBe(DEFAULT_MASTER_STYLE_ID)
    expect(resolveMasterStyle(null).id).toBe(DEFAULT_MASTER_STYLE_ID)
    expect(resolveMasterStyle(undefined).id).toBe(DEFAULT_MASTER_STYLE_ID)
  })

  it('LEGACY_MASTER_ID_MAP covers every shipped monochrome master style', () => {
    // Reverse the map so we can check that every modern id is reachable
    // from at least one legacy id — guarantees rehydration of saved
    // placements never silently loses a style. Multicolour masters are
    // post-merge so they don't have legacy aliases; restrict the check
    // to the monochrome family that pre-dates the registry split.
    const modern = new Set(Object.values(LEGACY_MASTER_ID_MAP))
    for (const s of masterStyles()) {
      if ((s.mode ?? 'monochrome') !== 'monochrome') continue
      expect(modern, `no legacy id maps to ${s.id}`).toContain(s.id)
    }
  })

  it('ALGORITHMS exposes every backend renderer the UI ever picks', () => {
    // Spot-check the headline algorithm ids — if any of these go
    // missing from the registry, the picker / param form would
    // silently drop knobs.
    for (const id of [
      'direct',
      'halftone',
      'stippling',
      'crosshatch',
      'contours',
      'edges',
      'spiral',
      'scanlines',
      'tsp',
    ]) {
      expect((ALGORITHMS as Record<string, unknown>)[id]).toBeDefined()
    }
  })

  it('layerStyles filters by applicableTo', () => {
    const imageOnly = layerStyles('image')
    for (const s of imageOnly) expect(s.applicableTo).toContain('image')
    const textStyles = layerStyles('text')
    for (const s of textStyles) expect(s.applicableTo).toContain('text')
  })
})
