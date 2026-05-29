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

test('Spiral (tonal) feeds bandRecipe spacing + amplitude per band', () => {
  const d = useBitmapDraft()
  // Tonal spiral is a shaded (luminance_bands) style now.
  d.bitmap.value.segmentation_method = 'luminance_bands'
  d.bitmap.value.num_bands = 3
  d.monoMasterStyleId.value = 'spiral-master'
  d.setMonoKnob('spiral-master', 'spacing_px', 5.5)
  d.setMonoKnob('spiral-master', 'wave_amp_min', 0.2)
  d.setMonoKnob('spiral-master', 'wave_amp_max', 6)
  const payload = d.buildBitmapOptions()
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes.length).toBe(3)
  expect(recipes[0]!.algorithm).toBe('spiral')
  const dark = recipes[0]!.algorithm_options as Record<string, unknown>
  const light = recipes[2]!.algorithm_options as Record<string, unknown>
  // spacing_px is constant across bands (shared spiral path)...
  expect(dark.spacing_px).toBe(5.5)
  expect(light.spacing_px).toBe(5.5)
  // ...while the radial wobble amplitude lerps darkest → lightest.
  expect(dark.wave_amp_px).toBeCloseTo(6)
  expect(light.wave_amp_px).toBeCloseTo(0.2)
})

test('Engraving wave_period overrides scanlines wave_period_px', () => {
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
    expect((r.algorithm_options as Record<string, unknown>).wave_period_px).toBe(18)
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
