import { beforeEach, describe, expect, it } from 'vitest'
import { useBitmapDraft } from './useBitmapDraft'
import {
  buildMonoBandRecipes,
  defaultMono,
  defaultMonoStyleKnobs,
  interpolatedBandOptions,
  isMonoDirty,
  markMonoCommitted,
  monoRecipeForBand,
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
        knob_units: 'mm',
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

  it('rescales px-era mono_knobs payloads (no knob_units marker) into mm', () => {
    rehydrateMonoFromOptions({
      mono_knobs: {
        ink_color: '#112233',
        perStyle: {
          // 22 px at the A4 reference scale (297 mm / 800 px) ≈ 8.17 mm.
          engraving: { wave_period: 22, spacing_min: 2.5 },
        },
      },
    })
    const mono = useMonoRecipe().mono.value
    expect(mono.perStyle.engraving!.wave_period).toBeCloseTo(8.17, 2)
    expect(mono.perStyle.engraving!.spacing_min).toBeCloseTo(0.93, 2)
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
      expect((r.algorithm_options as Record<string, unknown>).wave_period_mm).toBe(17)
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

  it('drives the knob-tuned recipe for the newly added shaded styles', () => {
    // flow-field, voronoi-shade, hilbert/gosper-fill, squiggle-shade and
    // concentric-rings all expose knob-driven recipes; spot-check that the
    // operator's knob reaches the emitted band options (not just the
    // hardcoded bandRecipe fallback).
    setMonoMasterStyleId('flowfield-master')
    setMonoKnob('flowfield-master', 'spacing_min', 5)
    setMonoKnob('flowfield-master', 'spacing_max', 5)
    const flow = buildMonoBandRecipes('luminance_bands', 3)
    expect(flow!.length).toBe(3)
    for (const r of flow!) {
      expect(r.algorithm).toBe('flowfield')
      // Both endpoints pinned to 5 → every band lands on 5 regardless of lerp.
      expect((r.algorithm_options as Record<string, unknown>).seed_spacing_mm).toBeCloseTo(5)
    }

    setMonoMasterStyleId('voronoi-shade')
    const vor = buildMonoBandRecipes('luminance_bands', 2)
    expect(vor!.every((r) => r.algorithm === 'voronoi_stipple')).toBe(true)
    // voronoi-shade and stippling-shade share the same density slider, so
    // their darkest/lightest density defaults must match for a consistent
    // tonal ramp between the two pointillist masters.
    const vorKnobs = defaultMonoStyleKnobs('voronoi-shade')
    const stipKnobs = defaultMonoStyleKnobs('stippling-shade')
    expect(vorKnobs.density_min).toBe(stipKnobs.density_min)
    expect(vorKnobs.density_max).toBe(stipKnobs.density_max)

    setMonoMasterStyleId('concentric-rings')
    const rings = buildMonoBandRecipes('luminance_bands', 2)
    expect(rings![0]!.algorithm).toBe('concentric_offset')
    // Darkest band carries the most rings (rings_max end of the lerp).
    const r0 = rings![0]!.algorithm_options as Record<string, unknown>
    const r1 = rings![1]!.algorithm_options as Record<string, unknown>
    expect(r0.max_rings as number).toBeGreaterThanOrEqual(r1.max_rings as number)
  })

  it('drives the low-poly and scribble shaded styles from their knobs', () => {
    setMonoMasterStyleId('lowpoly')
    setMonoKnob('lowpoly', 'density_min', 0.01)
    setMonoKnob('lowpoly', 'density_max', 0.01)
    const lp = buildMonoBandRecipes('luminance_bands', 3)
    expect(lp!.every((r) => r.algorithm === 'lowpoly')).toBe(true)
    for (const r of lp!) {
      expect((r.algorithm_options as Record<string, unknown>).density).toBeCloseTo(0.01)
    }

    setMonoMasterStyleId('scribble')
    const sc = buildMonoBandRecipes('luminance_bands', 2)
    expect(sc![0]!.algorithm).toBe('scribble')
    // Darkest band crosses → two angles; lighter band keeps one.
    const sc0 = sc![0]!.algorithm_options as Record<string, unknown>
    const sc1 = sc![1]!.algorithm_options as Record<string, unknown>
    expect((sc0.angles as number[]).length).toBe(2)
    expect((sc1.angles as number[]).length).toBe(1)
  })

  it('emits one direct recipe for the silhouette binary style', () => {
    setMonoMasterStyleId('silhouette')
    const recipes = buildMonoBandRecipes('thresholds', 4)
    expect(recipes!.length).toBe(1)
    expect(recipes![0]!.algorithm).toBe('direct')
  })

  it('emits a 2-opt tour for the tsp-optimized binary style', () => {
    setMonoMasterStyleId('tsp-optimized')
    setMonoKnob('tsp-optimized', 'density', 0.06)
    const recipes = buildMonoBandRecipes('thresholds', 3)
    expect(recipes!.length).toBe(1)
    expect(recipes![0]!.algorithm).toBe('tsp_opt')
    const opts = recipes![0]!.algorithm_options as Record<string, unknown>
    expect(opts.density).toBeCloseTo(0.06)
    expect(opts.method).toBe('nn_2opt')
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
    setMonoBandOverride('engraving', 1, { wave_period_mm: 99, spacing_mm: 4 })

    const recipes = buildMonoBandRecipes('luminance_bands', 3)
    expect(recipes!.length).toBe(3)
    const pinned = recipes![1]!.algorithm_options as Record<string, unknown>
    expect(pinned.wave_period_mm).toBe(99)
    expect(pinned.spacing_mm).toBe(4)
    // Bands 0 and 2 still go through the interpolation pipeline.
    const band0 = recipes![0]!.algorithm_options as Record<string, unknown>
    expect(band0.wave_period_mm).not.toBe(99)
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
    setMonoBandOverride('engraving', 1, { wave_period_mm: 999 })

    const opts = interpolatedBandOptions(1, 3)
    expect(opts.wave_period_mm).not.toBe(999)
    expect(typeof opts.spacing_mm).toBe('number')
  })
})

describe('generic algoOverrides knob (2026-06 tonal masters)', () => {
  beforeEach(() => {
    resetMonoRecipe()
    markMonoCommitted()
  })

  it('merges algoOverrides over the registry bandRecipe defaults', () => {
    // ridge-pulsar has no bespoke case in recipeFromKnobs — the default
    // branch must merge the schema-form overrides over bandRecipe().
    setMonoMasterStyleId('ridge-pulsar')
    setMonoKnob('ridge-pulsar', 'algoOverrides', { amp_mm: 22, occlude: false })
    const recipe = monoRecipeForBand(0, 1)
    expect(recipe).not.toBeNull()
    expect(recipe!.algorithm).toBe('ridge_lines')
    expect(recipe!.algorithm_options.amp_mm).toBe(22)
    expect(recipe!.algorithm_options.occlude).toBe(false)
    // Untouched options keep the registry default (1.9 mm ≈ the old
    // 5 px pitch at the A4 reference scale).
    expect(recipe!.algorithm_options.spacing_mm).toBe(1.9)
  })

  it('without overrides the registry bandRecipe passes through untouched', () => {
    setMonoMasterStyleId('dither-print')
    const recipe = monoRecipeForBand(0, 1)
    expect(recipe).not.toBeNull()
    expect(recipe!.algorithm).toBe('dither')
    expect(recipe!.algorithm_options.method).toBe('floyd')
  })
})
