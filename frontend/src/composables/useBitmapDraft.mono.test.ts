import { beforeEach, describe, expect, it } from 'vitest'
import { useBitmapDraft } from './useBitmapDraft'

// Non-regression suite for the MONO RECIPE concern on
// ``useBitmapDraft``. The existing ``useBitmapDraft.test.ts`` covers
// per-style knob → band recipe propagation (TSP, Spiral, Engraving)
// but not the rest of the mono lifecycle: ink color persistence,
// rehydrate from ``mono_knobs``, dirty tracking, the
// ``setMasterStyle`` coupling with bitmap segmentation, and per-band
// overrides.
//
// Added before splitting the mono slice out of ``useBitmapDraft``
// (L6 #2) so the refactor is verifiable against observable behaviour.

function reset(): void {
  useBitmapDraft().rehydrateDraft({ placement: null, installedPenColors: [] })
}

describe('mono ink color', () => {
  beforeEach(reset)

  it('setMonoInkColor mutates the mono knob and ships in the /upload payload', () => {
    const d = useBitmapDraft()
    // Force monochrome so the upload payload carries the ink color
    // (it's gated on print mode).
    d.bitmap.value.segmentation_method = 'luminance_bands'
    d.setMonoInkColor('#ff8800')
    expect(d.mono.value.ink_color).toBe('#ff8800')

    const payload = d.buildBitmapOptions()
    expect(payload.mono_ink_color).toBe('#ff8800')
    expect((payload.mono_knobs as Record<string, unknown>).ink_color).toBe('#ff8800')
  })
})

describe('mono master style id rehydrate', () => {
  beforeEach(reset)

  it('restores the legacy master_style_id field from last_options', () => {
    // Pre-multicolour placements stored a single ``master_style_id``;
    // the rehydrate path must still honour it.
    const d = useBitmapDraft()
    d.rehydrateDraft({
      placement: { last_options: { master_style_id: 'engraving' } },
      installedPenColors: [],
    })
    expect(d.monoMasterStyleId.value).toBe('engraving')
  })

  it('mono_master_style_id wins over the legacy field when both are present', () => {
    // Post-multicolour placements ship both for compat; the explicit
    // per-mode field must take precedence so the picker reflects what
    // the operator actually committed.
    const d = useBitmapDraft()
    d.rehydrateDraft({
      placement: {
        last_options: {
          master_style_id: 'engraving',
          mono_master_style_id: 'pencil',
        },
      },
      installedPenColors: [],
    })
    expect(d.monoMasterStyleId.value).toBe('pencil')
  })
})

describe('mono_knobs rehydrate', () => {
  beforeEach(reset)

  it('merges persisted perStyle overrides over the defaults from MONO_STYLE_DEFAULTS', () => {
    // A placement that pre-dates a newly added MONO_STYLE_DEFAULTS
    // field should still get that field's default; the persisted
    // override is layered on top of the freshly synthesised defaults.
    const d = useBitmapDraft()
    d.rehydrateDraft({
      placement: {
        last_options: {
          mono_knobs: {
            ink_color: '#112233',
            knob_units: 'mm',
            perStyle: {
              engraving: { wave_period: 22 },
            },
          },
        },
      },
      installedPenColors: [],
    })
    expect(d.mono.value.ink_color).toBe('#112233')
    expect(d.mono.value.perStyle.engraving!.wave_period).toBe(22)
    // Defaults are still present for fields the persisted override
    // didn't touch (sentinel: every other engraving knob exists).
    expect(d.mono.value.perStyle.engraving!.spacing_min).toBeDefined()
  })

  it('accepts mono_ink_color at the top level as a belt-and-braces fallback', () => {
    // Older payload formats dropped the top-level field alongside the
    // canonical mono_knobs.ink_color; the rehydrate path must pick it
    // up either way.
    const d = useBitmapDraft()
    d.rehydrateDraft({
      placement: { last_options: { mono_ink_color: '#abcdef' } },
      installedPenColors: [],
    })
    expect(d.mono.value.ink_color).toBe('#abcdef')
  })
})

describe('setMasterStyle ↔ bitmap segmentation coupling', () => {
  beforeEach(reset)

  it('mutates both the mono master id and the bitmap segmentation method', () => {
    // ``engraving`` is a luminance_bands-based shaded master. Calling
    // setMasterStyle must rewrite both _monoMasterStyleId AND the
    // bitmap segmentation method so the next /preview round-trip
    // matches what the picker UI shows.
    const d = useBitmapDraft()
    d.setMasterStyle('engraving')
    expect(d.monoMasterStyleId.value).toBe('engraving')
    expect(d.bitmap.value.segmentation_method).toBe('luminance_bands')
    expect(d.printMode.value).toBe('monochrome')
  })

  it('switching to a binary master (tsp) sets thresholds with one entry', () => {
    // TSP is binary monochrome — the resulting segmentation must be
    // thresholds with a single cut so ``_printMode`` resolves to
    // monochrome and ``buildBandRecipes`` emits exactly one recipe.
    const d = useBitmapDraft()
    d.setMasterStyle('tsp')
    expect(d.monoMasterStyleId.value).toBe('tsp')
    expect(d.bitmap.value.segmentation_method).toBe('thresholds')
    expect(d.bitmap.value.thresholds.length).toBe(1)
    expect(d.printMode.value).toBe('monochrome')
  })
})

describe('mono dirty tracking', () => {
  beforeEach(reset)

  it('flips isDirty after each mono mutation and clears on markCommitted', () => {
    const d = useBitmapDraft()
    d.markCommitted()
    expect(d.isDirty.value).toBe(false)

    d.setMonoInkColor('#aabbcc')
    expect(d.isDirty.value).toBe(true)

    d.markCommitted()
    expect(d.isDirty.value).toBe(false)

    d.setMonoKnob('engraving', 'wave_period', 25)
    expect(d.isDirty.value).toBe(true)

    d.markCommitted()
    expect(d.isDirty.value).toBe(false)

    d.setMonoAdvancedMode(true)
    expect(d.isDirty.value).toBe(true)
  })

  it('setMonoBandOverride participates in dirty tracking', () => {
    const d = useBitmapDraft()
    d.markCommitted()
    d.setMonoBandOverride('engraving', 1, { spacing_mm: 3.5 })
    expect(d.isDirty.value).toBe(true)
  })
})

describe('interpolatedBandOptions', () => {
  beforeEach(reset)

  it('returns interpolated algorithm_options that ignore the perBand override', () => {
    // The "Advanced (per band)" drawer pre-fills each card with the
    // interpolated value the recipe would produce — INDEPENDENTLY of
    // any literal perBand pin. Pinning band 1 with a sentinel value
    // must not leak into ``interpolatedBandOptions(1, 3)``.
    const d = useBitmapDraft()
    d.bitmap.value.segmentation_method = 'luminance_bands'
    d.bitmap.value.num_bands = 3
    d.setMasterStyle('engraving')
    d.setMonoBandOverride('engraving', 1, { wave_period_mm: 999 })

    const opts = d.interpolatedBandOptions(1, 3)
    expect(opts.wave_period_mm).not.toBe(999)
    expect(typeof opts.spacing_mm).toBe('number')
  })
})

describe('setMonoBandOverride pin & clear', () => {
  beforeEach(reset)

  it('pins a perBand override and propagates it into band_recipes', () => {
    const d = useBitmapDraft()
    d.bitmap.value.segmentation_method = 'luminance_bands'
    d.bitmap.value.num_bands = 3
    d.setMasterStyle('engraving')
    d.setMonoBandOverride('engraving', 1, { wave_period_mm: 99, spacing_mm: 4 })

    const payload = d.buildBitmapOptions()
    const recipes = payload.band_recipes as Array<Record<string, unknown>>
    expect(recipes.length).toBe(3)
    const pinnedOpts = recipes[1]!.algorithm_options as Record<string, unknown>
    expect(pinnedOpts.wave_period_mm).toBe(99)
    expect(pinnedOpts.spacing_mm).toBe(4)
  })
})

describe('getMonoStyleKnobs auto-creates entries', () => {
  beforeEach(reset)

  it('returns a fresh defaults object for a style id missing from perStyle', () => {
    // Defensive: a freshly added master style without a perStyle entry
    // must still get its defaults synthesised on first access so the
    // params components never read ``undefined``.
    const d = useBitmapDraft()
    delete d.mono.value.perStyle.engraving
    const knobs = d.getMonoStyleKnobs('engraving')
    expect(knobs).toBeDefined()
    expect(d.mono.value.perStyle.engraving).toBe(knobs)
  })
})
