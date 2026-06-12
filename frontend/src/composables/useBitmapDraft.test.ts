import { test, expect } from 'vitest'
import { useBitmapDraft } from './useBitmapDraft'

test('TSP knob slider feeds bandRecipe density on /preview payload', () => {
  const d = useBitmapDraft()
  // Force binary mono via TSP master style
  d.bitmap.value.segmentation_method = 'thresholds'
  d.bitmap.value.thresholds = [0.5]
  d.monoMasterStyleId.value = 'tsp'
  d.setMonoKnob('tsp', 'density', 0.077)
  const payload = d.buildBitmapOptions()
  expect(d.printMode.value).toBe('monochrome')
  expect(Array.isArray(payload.band_recipes)).toBe(true)
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(1)
  expect(recipes[0]!.algorithm).toBe('tsp')
  const opts = recipes[0]!.algorithm_options as Record<string, unknown>
  expect(opts.density).toBeCloseTo(0.077)
})

test('Spiral (tonal) feeds spacing + wavelength + strength', () => {
  const d = useBitmapDraft()
  // Tonal spiral is a single-band luminance_bands style; the per-pixel
  // wobble amplitude is computed backend-side from the tone map, so the
  // recipe only carries the spiral geometry knobs.
  d.bitmap.value.segmentation_method = 'luminance_bands'
  d.bitmap.value.num_bands = 1
  d.monoMasterStyleId.value = 'spiral-master'
  d.setMonoKnob('spiral-master', 'spacing_mm', 5.5)
  d.setMonoKnob('spiral-master', 'wavelength_mm', 10)
  d.setMonoKnob('spiral-master', 'tone_strength', 0.6)
  const payload = d.buildBitmapOptions()
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes[0]!.algorithm).toBe('spiral')
  const o = recipes[0]!.algorithm_options as Record<string, unknown>
  expect(o.spacing_mm).toBe(5.5)
  expect(o.wavelength_mm).toBe(10)
  expect(o.tone_strength).toBe(0.6)
})

test('Engraving wave_period overrides scanlines wave_period_mm', () => {
  const d = useBitmapDraft()
  d.bitmap.value.segmentation_method = 'luminance_bands'
  d.bitmap.value.num_bands = 3
  d.monoMasterStyleId.value = 'engraving'
  d.setMonoKnob('engraving', 'wave_period', 18)
  const payload = d.buildBitmapOptions()
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(3)
  for (const r of recipes) {
    expect(r.algorithm).toBe('scanlines')
    expect((r.algorithm_options as Record<string, unknown>).wave_period_mm).toBe(18)
  }
})

test('switching to monochrome yields a single band / layer by default', () => {
  const d = useBitmapDraft()
  // Reset to pristine defaults (no committed placement).
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  const overwritten = d.setPrintMode('monochrome')
  // No manual-tweak warning fields when coming from a clean slate.
  expect(overwritten).toEqual([])
  expect(d.printMode.value).toBe('monochrome')
  expect(d.bitmap.value.segmentation_method).toBe('luminance_bands')
  // The promise of monochrome mode: one layer, one pen.
  expect(d.bitmap.value.num_bands).toBe(1)
  expect(d.expectedLayerCount.value).toBe(1)
  const payload = d.buildBitmapOptions()
  expect((payload.segmentation_options as Record<string, unknown>).num_bands).toBe(1)
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(1)
})

test('bumping the shading slider adds bands (and layers) on demand', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.setPrintMode('monochrome')
  expect(d.expectedLayerCount.value).toBe(1)
  // Operator opts into tonal shading via the bands slider.
  d.bitmap.value.num_bands = 4
  expect(d.expectedLayerCount.value).toBe(4)
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(4)
})

test('shading bands accept up to 20 and survive a master-style switch', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.setPrintMode('monochrome')
  // High band count (was capped at 6) is honoured.
  d.bitmap.value.num_bands = 20
  expect(d.expectedLayerCount.value).toBe(20)
  // Switching shaded master styles preserves the operator's band count
  // (20 is in range, not reset to the style default of 1).
  d.setMasterStyle('halftone-shade')
  expect(d.bitmap.value.num_bands).toBe(20)
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(20)
})

test('advanced_mode default off and toggles via setter', () => {
  const d = useBitmapDraft()
  d.setMonoAdvancedMode(false)
  expect(d.mono.value.advanced_mode).toBe(false)
  d.setMonoAdvancedMode(true)
  expect(d.mono.value.advanced_mode).toBe(true)
})

test('color-crosshatch band recipes give distinct angles per cluster at default step', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  // Multicolour kmeans path with 4 clusters.
  d.bitmap.value.segmentation_method = 'kmeans'
  d.bitmap.value.num_colors = 4
  d.setMulticolorMasterStyle('color-crosshatch', { force: true })
  expect(d.printMode.value).toBe('multicolor')
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(4)
  const angles = recipes.map((r) => (r.algorithm_options as Record<string, unknown>).angle_deg)
  // Default angle_step (45) must reduce to the registry colorRecipe
  // fallback (0/45/90/135) so the knob-driven and propagation paths
  // agree — and crucially the 4 clusters get 4 distinct angles (the old
  // i*step formula collapsed them onto 0/90/0/90).
  expect(angles).toEqual([0, 45, 90, 135])
  expect(new Set(angles).size).toBe(4)
})

test('color-eulerian band recipes give distinct angles per cluster at default step', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.bitmap.value.segmentation_method = 'kmeans'
  d.bitmap.value.num_colors = 4
  d.setMulticolorMasterStyle('color-eulerian', { force: true })
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  const angles = recipes.map((r) => (r.algorithm_options as Record<string, unknown>).angle_deg)
  expect(angles).toEqual([0, 45, 90, 135])
})

// >4-colour regression suite: band recipes must track the operator's
// colour count past the historical default of 4, for every method that
// can carry a multicolour job.

test('kmeans band recipes track num_colors above 4 (6, 8, 16)', () => {
  const d = useBitmapDraft()
  for (const n of [6, 8, 16]) {
    d.rehydrateDraft({ placement: null, installedPenColors: [] })
    d.bitmap.value.segmentation_method = 'kmeans'
    d.bitmap.value.num_colors = n
    d.setMulticolorMasterStyle('color-crosshatch', { force: true })
    const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
    expect(recipes.length).toBe(n)
  }
})

test('color-crosshatch keeps 16 clusters on 16 distinct hatch angles', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.bitmap.value.segmentation_method = 'kmeans'
  d.bitmap.value.num_colors = 16
  d.setMulticolorMasterStyle('color-crosshatch', { force: true })
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  const angles = recipes.map((r) => (r.algorithm_options as Record<string, unknown>).angle_deg)
  // Past the 8-angle base list the wrap offset (7.5°/wrap) keeps every
  // cluster on its own direction instead of repeating the first eight.
  expect(new Set(angles).size).toBe(16)
})

test('color-dashes gives distinct angles per cluster at default step', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.bitmap.value.segmentation_method = 'kmeans'
  d.bitmap.value.num_colors = 6
  d.setMulticolorMasterStyle('color-dashes', { force: true })
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  const angles = recipes.map((r) => (r.algorithm_options as Record<string, unknown>).angle_deg)
  // The old ``i * step + base`` collapsed the default step onto 0/90.
  expect(new Set(angles).size).toBe(6)
})

test('fixed_palette band recipes follow the deduped palette length', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.setMulticolorMasterStyle('color-crosshatch', { force: true })
  d.bitmap.value.segmentation_method = 'fixed_palette'
  // 6 chips with one duplicate → the backend merges to 5 layers.
  d.bitmap.value.palette = ['#000000', '#ff0000', '#00ff00', '#0000ff', '#888888', '#888888']
  d.bitmap.value.num_colors = 6
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(5)
  expect(d.expectedLayerCount.value).toBe(5)
})

test('pens-follow palette wires as kmeans_lab + ink_pool (not fixed_palette)', () => {
  const d = useBitmapDraft()
  const pens = ['#000000', '#ff0000', '#0000cc', '#888888', '#44dd44', '#ffcc00']
  d.rehydrateDraft({ placement: null, installedPenColors: pens })
  d.setMulticolorMasterStyle('color-flat', { force: true })
  d.paletteFollowsPens.value = true
  // Mirror what the StyleTab watcher writes in pens mode.
  d.bitmap.value.segmentation_method = 'fixed_palette'
  d.bitmap.value.palette = [...pens]
  d.bitmap.value.num_colors = 6
  const payload = d.buildBitmapOptions()
  // Colour-distance snapping starves saturated pens on low-saturation
  // photos; the wire ships perceptual clustering + the ink remap so
  // every requested pen shows up whatever the source colours are.
  expect(payload.segmentation_method).toBe('kmeans_lab')
  // Pool size + 1: drop_background (default on) lets the paper-white
  // background win its own cluster before being dropped, so k = pool
  // size silently cost one ink.
  expect(payload.num_colors).toBe(7)
  expect(payload.ink_pool).toEqual(pens)
  expect(payload.segmentation_options).toEqual({})
})

test('pens-follow ships the FULL rack as ink_pool, num_colors caps the clusters', () => {
  // Regression for "blue drawn as red, green as yellow": reducing the
  // colour count truncated the display palette to the first N magazine
  // slots and sent THAT as the ink_pool, so clusters could only snap to
  // the first few inks. The full rack must reach the backend so every
  // cluster lands on its perceptually-nearest owned ink; num_colors only
  // caps how many clusters the image is reduced to.
  const d = useBitmapDraft()
  const fullRack = [
    '#000000',
    '#ffffff',
    '#ff0000',
    '#ffff00',
    '#00ff00',
    '#0000ff',
    '#ff00ff',
    '#00ffff',
    '#ff8800',
    '#8800ff',
    '#888888',
  ]
  d.rehydrateDraft({ placement: null, installedPenColors: fullRack })
  d.setMulticolorMasterStyle('color-flat', { force: true })
  d.paletteFollowsPens.value = true
  d.bitmap.value.segmentation_method = 'fixed_palette'
  // What the StyleTab watcher writes: full rack in pensFullPool, palette
  // truncated to num_colors for the colour-count displays.
  d.pensFullPool.value = [...fullRack]
  d.bitmap.value.palette = fullRack.slice(0, 4)
  d.bitmap.value.num_colors = 4
  const payload = d.buildBitmapOptions()
  expect(payload.segmentation_method).toBe('kmeans_lab')
  // ink_pool is the WHOLE rack — blue/green stay reachable.
  expect(payload.ink_pool).toEqual(fullRack)
  // num_colors = chosen 4 (+1 for the dropped background), NOT the rack size.
  expect(payload.num_colors).toBe(5)
})

test('manual fixed palette still wires as fixed_palette (no ink_pool)', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.setMulticolorMasterStyle('color-flat', { force: true })
  d.paletteFollowsPens.value = false
  d.bitmap.value.segmentation_method = 'fixed_palette'
  d.bitmap.value.palette = ['#000000', '#ff0000', '#0000cc']
  const payload = d.buildBitmapOptions()
  expect(payload.segmentation_method).toBe('fixed_palette')
  expect(payload.ink_pool).toBeUndefined()
  expect((payload.segmentation_options as Record<string, unknown>).palette).toEqual([
    '#000000',
    '#ff0000',
    '#0000cc',
  ])
})

test('rehydrate restores pens mode from a persisted ink_pool', () => {
  const d = useBitmapDraft()
  const pens = ['#000000', '#ff0000', '#0000cc', '#888888', '#44dd44', '#ffcc00']
  const placement = {
    last_options: {
      segmentation_method: 'kmeans_lab',
      num_colors: 4,
      // Pool truncated to the first 4 pens by the colour-count slider.
      ink_pool: pens.slice(0, 4),
      segmentation_options: {},
    },
  }
  d.rehydrateDraft({
    placement: placement as never,
    installedPenColors: pens,
  })
  // Draft-internal pens-mode representation restored: fixed_palette +
  // the pool as palette + follows-pens inferred by prefix match (the
  // pool is the first N pens, not the full rack).
  expect(d.bitmap.value.segmentation_method).toBe('fixed_palette')
  expect(d.bitmap.value.palette).toEqual(pens.slice(0, 4))
  expect(d.paletteFollowsPens.value).toBe(true)
  expect(d.bitmap.value.num_colors).toBe(4)
})

test('band recipes fall back to num_colors (not 4) on a mismatched method', () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  d.setMulticolorMasterStyle('color-crosshatch', { force: true })
  // Operator hand-picked a method outside the multicolour family on the
  // SVG tab (a generic multi-cut thresholds split); the recipe count
  // must still honour their colour count instead of the historical
  // hardcoded 4.
  d.bitmap.value.segmentation_method = 'thresholds'
  d.bitmap.value.thresholds = [0.3, 0.6]
  d.bitmap.value.num_colors = 6
  const recipes = d.buildBitmapOptions().band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(6)
})
