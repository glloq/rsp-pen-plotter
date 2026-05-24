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

test('Spiral knob slider feeds bandRecipe spacing_px', () => {
  const d = useBitmapDraft()
  d.bitmap.value.segmentation_method = 'thresholds'
  d.bitmap.value.thresholds = [0.5]
  d.monoMasterStyleId.value = 'spiral-master'
  d.setMonoKnob('spiral-master', 'spacing_px', 5.5)
  const payload = d.buildBitmapOptions()
  const recipes = payload.band_recipes as Array<Record<string, unknown>>
  expect(recipes[0]!.algorithm).toBe('spiral')
  const opts = recipes[0]!.algorithm_options as Record<string, unknown>
  expect(opts.spacing_px).toBe(5.5)
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

test('advanced_mode default off and toggles via setter', () => {
  const d = useBitmapDraft()
  d.setMonoAdvancedMode(false)
  expect(d.mono.value.advanced_mode).toBe(false)
  d.setMonoAdvancedMode(true)
  expect(d.mono.value.advanced_mode).toBe(true)
})
