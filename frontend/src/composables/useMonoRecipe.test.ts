import { beforeEach, describe, expect, it } from 'vitest'
import { useBitmapDraft } from './useBitmapDraft'
import {
  buildMonoBandRecipes,
  defaultMono,
  defaultMonoStyleKnobs,
  interpolatedBandOptions,
  isMonoDirty,
  markMonoCommitted,
  rehydrateMonoFromOptions,
  resetMonoRecipe,
  setMonoBandOverride,
  setMonoInkColor,
  setMonoKnob,
  setMonoMasterStyleId,
  useMonoRecipe,
} from './useMonoRecipe'

// The mono composable is the L6 #2 extraction of the mono recipe
// slice that used to live in ``useBitmapDraft``. These tests pin
// down the standalone surface (defaults, rehydrate, dirty, commit,
// recipe synthesis) AND the singleton-sharing contract with
// ``useBitmapDraft``: MasterStyleParams binds against the refs
// ``useBitmapDraft().mono`` / ``.monoMasterStyleId`` returns, so
// both composables must hand out the same underlying refs.

describe('useMonoRecipe singleton contract', () => {
  beforeEach(() => {
    resetMonoRecipe()
    markMonoCommitted()
  })

  it('exposes the same refs as useBitmapDraft', () => {
    // The L6 split is invisible to MasterStyleParams' v-model bindings
    // only if both composables hand out THE same singletons. Cross-
    // mutate to prove it for each ref the bitmap composable exposes.
    const mono = useMonoRecipe()
    const bitmap = useBitmapDraft()
    expect(mono.mono).toBe(bitmap.mono)
    expect(mono.monoMasterStyleId).toBe(bitmap.monoMasterStyleId)
    expect(mono.monoPenSlot).toBe(bitmap.monoPenSlot)

    mono.mono.value.ink_color = '#abcdef'
    expect(bitmap.mono.value.ink_color).toBe('#abcdef')

    bitmap.monoMasterStyleId.value = 'engraving'
    expect(mono.monoMasterStyleId.value).toBe('engraving')
  })

  it('reset() puts the singleton back to defaults', () => {
    setMonoInkColor('#ff0000')
    setMonoMasterStyleId('engraving')
    setMonoKnob('engraving', 'wave_period', 25)

    resetMonoRecipe()
    expect(useMonoRecipe().mono.value).toEqual(defaultMono())
    expect(useMonoRecipe().monoMasterStyleId.value).not.toBe('engraving')
  })
})

describe('rehydrateMonoFromOptions', () => {
  beforeEach(() => {
    resetMonoRecipe()
  })

  it('is a no-op when last_options is null / undefined / not an object', () => {
    rehydrateMonoFromOptions(null)
    rehydrateMonoFromOptions(undefined)
    expect(useMonoRecipe().mono.value).toEqual(defaultMono())
  })

  it('mono_master_style_id wins over the legacy master_style_id', () => {
    // Mirrors the lifecycle test on useBitmapDraft but exercises the
    // standalone helper directly so future callers (e.g. a per-
    // placement plan resolver) can rely on the same precedence.
    rehydrateMonoFromOptions({
      master_style_id: 'engraving',
      mono_master_style_id: 'pencil',
    })
    expect(useMonoRecipe().monoMasterStyleId.value).toBe('pencil')
  })

  it('merges mono_knobs.perStyle over the synthesized defaults', () => {
    rehydrateMonoFromOptions({
      mono_knobs: {
        ink_color: '#112233',
        perStyle: {
          engraving: { wave_period: 22 },
        },
      },
    })
    const mono = useMonoRecipe().mono.value
    expect(mono.ink_color).toBe('#112233')
    expect(mono.perStyle.engraving!.wave_period).toBe(22)
    // Untouched fields still pick up their MONO_STYLE_DEFAULTS value.
    expect(mono.perStyle.engraving!.spacing_min).toBeDefined()
  })

  it('mono_ink_color at the top level wins over mono_knobs.ink_color', () => {
    // Belt-and-braces format: when both fields ship, the top-level
    // override is applied last so older payloads that dropped just
    // ``mono_knobs`` still hydrate.
    rehydrateMonoFromOptions({
      mono_knobs: { ink_color: '#aaaaaa' },
      mono_ink_color: '#bbbbbb',
    })
    expect(useMonoRecipe().mono.value.ink_color).toBe('#bbbbbb')
  })
})

describe('isMonoDirty / markMonoCommitted', () => {
  beforeEach(() => {
    resetMonoRecipe()
    markMonoCommitted()
  })

  it('returns false right after markMonoCommitted', () => {
    expect(isMonoDirty.value).toBe(false)
  })

  it('flips true on a mutation and back to false after a fresh commit', () => {
    setMonoInkColor('#deadbe')
    expect(isMonoDirty.value).toBe(true)

    markMonoCommitted()
    expect(isMonoDirty.value).toBe(false)
  })
})

describe('defaultMonoStyleKnobs', () => {
  it('deep-copies the angles array so per-style tweaks do not bleed into the defaults', () => {
    // Sentinel: mutating one style's angles array must NOT affect the
    // MONO_STYLE_DEFAULTS table — a regression here would silently
    // change every freshly created draft.
    const a = defaultMonoStyleKnobs('pencil')
    const b = defaultMonoStyleKnobs('pencil')
    if (Array.isArray(a.angles)) {
      a.angles.push(999)
      expect(b.angles).not.toContain(999)
    }
  })

  it('initialises perBand to an empty object so callers can write without a null check', () => {
    const knobs = defaultMonoStyleKnobs('engraving')
    expect(knobs.perBand).toEqual({})
  })
})

describe('buildMonoBandRecipes', () => {
  beforeEach(() => {
    resetMonoRecipe()
  })

  it('emits one recipe per band for luminance_bands mode', () => {
    setMonoMasterStyleId('engraving')
    setMonoKnob('engraving', 'wave_period', 17)

    const recipes = buildMonoBandRecipes('luminance_bands', 3)
    expect(recipes).toBeDefined()
    expect(recipes!.length).toBe(3)
    for (const r of recipes!) {
      expect(r.algorithm).toBe('scanlines')
      expect((r.algorithm_options as Record<string, unknown>).wave_period_px).toBe(17)
    }
  })

  it('emits exactly one recipe for thresholds (binary) mode regardless of numBands', () => {
    setMonoMasterStyleId('tsp')
    setMonoKnob('tsp', 'density', 0.08)

    const recipes = buildMonoBandRecipes('thresholds', 3)
    expect(recipes).toBeDefined()
    expect(recipes!.length).toBe(1)
    expect(recipes![0]!.algorithm).toBe('tsp')
    expect((recipes![0]!.algorithm_options as Record<string, unknown>).density).toBeCloseTo(0.08)
  })

  it('returns undefined for segmentation methods that do not produce mono recipes', () => {
    // kmeans / fixed_palette are multicolour segmentations; the mono
    // recipe builder must opt out so the caller can fall through to
    // the multicolour branch.
    expect(buildMonoBandRecipes('kmeans', 3)).toBeUndefined()
    expect(buildMonoBandRecipes('fixed_palette', 3)).toBeUndefined()
  })

  it('honours a perBand override on the pinned band only', () => {
    setMonoMasterStyleId('engraving')
    setMonoBandOverride('engraving', 1, { wave_period_px: 99, spacing_px: 4 })

    const recipes = buildMonoBandRecipes('luminance_bands', 3)
    expect(recipes!.length).toBe(3)
    const pinned = recipes![1]!.algorithm_options as Record<string, unknown>
    expect(pinned.wave_period_px).toBe(99)
    expect(pinned.spacing_px).toBe(4)
    // Bands 0 and 2 still go through the interpolation pipeline.
    const band0 = recipes![0]!.algorithm_options as Record<string, unknown>
    expect(band0.wave_period_px).not.toBe(99)
  })
})

describe('interpolatedBandOptions ignores perBand pins', () => {
  beforeEach(() => {
    resetMonoRecipe()
  })

  it('returns interpolated values even when the band is pinned', () => {
    // The drawer pre-fills the per-band card with the value the
    // interpolation pipeline WOULD produce, so the operator sees what
    // the pin diverges from. Pinning band 1 must not leak into the
    // pre-fill returned by ``interpolatedBandOptions(1, 3)``.
    setMonoMasterStyleId('engraving')
    setMonoBandOverride('engraving', 1, { wave_period_px: 999 })

    const opts = interpolatedBandOptions(1, 3)
    expect(opts.wave_period_px).not.toBe(999)
    expect(typeof opts.spacing_px).toBe('number')
  })
})
