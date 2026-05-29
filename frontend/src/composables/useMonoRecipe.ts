// Singleton owner of the EditModal's MONO RECIPE state — the slice
// that drives the monochrome ink color, the active mono master style,
// the per-style range knobs, and the per-band literal overrides that
// the /preview & /upload payloads consume as ``band_recipes``.
//
// Extracted from ``useBitmapDraft`` (L6 #2) so the mono lifecycle
// (defaults → rehydrate → dirty → commit → recipe synthesis) lives in
// a focused module. ``useBitmapDraft`` re-exports the types
// (``MonoStyleKnobs``, ``MonoKnobsDraft``) and the defaults
// (``defaultMono``, ``defaultMonoStyleKnobs``) so existing consumers
// — ``MasterStyleParams`` and the bitmap test suite — keep their
// import surface unchanged.
//
// The refs returned by ``useMonoRecipe()`` are the SAME singletons
// ``useBitmapDraft()`` returns; this matters for two coupling points
// that stay in ``useBitmapDraft``:
//   - ``_printMode`` reads ``_monoMasterStyleId`` to decide whether a
//     1-cut thresholds segmentation counts as binary monochrome
//   - ``setMasterStyle`` mutates ``_monoMasterStyleId`` AND calls
//     ``applyStyleSegmentation`` to rewrite the bitmap segmentation
//
// ``buildMonoBandRecipes`` is parametrised on ``segMethod`` and
// ``numBands`` instead of reading them off ``_bitmap`` so this
// module stays free of bitmap imports — the bitmap composable's
// ``buildBandRecipes`` does the dispatch and passes the inputs in.

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  resolveMasterStyle,
  DEFAULT_MASTER_STYLE_ID,
  MONO_STYLE_DEFAULTS,
  lerp,
  type PrintStyle,
} from '../data/printRegistry'

export type MonoStyleKnobs = {
  spacing_min?: number
  spacing_max?: number
  density_min?: number
  density_max?: number
  cell_min?: number
  cell_max?: number
  rings_min?: number
  rings_max?: number
  wave_min?: number
  wave_max?: number
  density?: number
  spacing_px?: number
  wave_period?: number
  // Tonal spiral: wobble spatial wavelength (px) + a 0..1 strength that
  // scales the per-pixel amplitude. Amplitude itself is computed in the
  // backend from the luminance map, not here.
  wavelength_px?: number
  tone_strength?: number
  dot_radius?: number
  stroke_width?: number
  angles?: number[]
  crossed_on_darkest?: boolean
  // Sparse map of literal per-band overrides. When present, the band
  // index in the map bypasses the interpolation pipeline and uses the
  // recorded ``algorithm_options`` verbatim (the "Advanced" drawer's
  // pin button writes here).
  perBand?: Record<number, Record<string, unknown>>
}

export type MonoKnobsDraft = {
  ink_color: string
  advanced_mode: boolean
  perStyle: Record<string, MonoStyleKnobs>
}

export function defaultMonoStyleKnobs(styleId: string): MonoStyleKnobs {
  const src = MONO_STYLE_DEFAULTS[styleId] ?? {}
  // Shallow clone with deep copy of the angles array so callers that
  // mutate one band's knobs don't accidentally rewrite the shared
  // defaults dict.
  const out: MonoStyleKnobs = { ...(src as MonoStyleKnobs) }
  if (Array.isArray(out.angles)) out.angles = [...out.angles]
  out.perBand = {}
  return out
}

export function defaultMono(): MonoKnobsDraft {
  const perStyle: Record<string, MonoStyleKnobs> = {}
  for (const id of Object.keys(MONO_STYLE_DEFAULTS)) {
    perStyle[id] = defaultMonoStyleKnobs(id)
  }
  return { ink_color: '#000000', advanced_mode: false, perStyle }
}

// ---- Singleton state ----
const _mono = ref<MonoKnobsDraft>(defaultMono())
const _monoMasterStyleId = ref<string>(DEFAULT_MASTER_STYLE_ID)
const _monoPenSlot = ref<number>(0)
const _baselineMono = ref<string>('')

function snap(value: unknown): string {
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

const _isMonoDirty = computed<boolean>(() => snap(_mono.value) !== _baselineMono.value)

// ---- Mutators (mono-only; setMasterStyle stays in useBitmapDraft
// since it also rewrites bitmap segmentation) ----

export function setMonoInkColor(color: string): void {
  _mono.value.ink_color = color
}

export function setMonoAdvancedMode(value: boolean): void {
  _mono.value.advanced_mode = value
}

export function getMonoStyleKnobs(styleId: string): MonoStyleKnobs {
  if (!_mono.value.perStyle[styleId]) {
    _mono.value.perStyle[styleId] = defaultMonoStyleKnobs(styleId)
  }
  return _mono.value.perStyle[styleId]!
}

export function setMonoKnob<K extends keyof MonoStyleKnobs>(
  styleId: string,
  key: K,
  value: MonoStyleKnobs[K],
): void {
  const knobs = getMonoStyleKnobs(styleId)
  knobs[key] = value
}

export function setMonoBandOverride(
  styleId: string,
  bandIndex: number,
  override: Record<string, unknown> | null,
): void {
  const knobs = getMonoStyleKnobs(styleId)
  if (!knobs.perBand) knobs.perBand = {}
  if (override === null) {
    delete knobs.perBand[bandIndex]
  } else {
    // Clone so the caller can keep mutating its own object without
    // bleeding into the pinned recipe.
    knobs.perBand[bandIndex] = { ...override }
  }
}

export function resetMonoStyleKnobs(styleId: string): void {
  _mono.value.perStyle[styleId] = defaultMonoStyleKnobs(styleId)
}

/**
 * Set the active mono master style id WITHOUT touching bitmap
 * segmentation. The full ``setMasterStyle`` (which also rewrites
 * ``segmentation_method`` / ``num_bands`` / ``thresholds`` / etc.)
 * lives in ``useBitmapDraft`` because it crosses the bitmap boundary.
 */
export function setMonoMasterStyleId(id: string): void {
  _monoMasterStyleId.value = id
}

// ---- Recipe synthesis ----

// Pick the i-th angle for a pencil-style band, cycling through the
// operator's chosen angle list. ``angles`` must be non-empty; callers
// guarantee this by falling back to MONO_STYLE_DEFAULTS.pencil.angles
// when the operator clears the list.
function pickAnglesForBand(i: number, _total: number, angles: number[]): number[] {
  if (angles.length === 0) return [45]
  // Single-angle list → every band uses that single angle (operator
  // explicitly asked for a uniform direction). Otherwise pick a
  // different angle per band so darker bands get visually denser
  // multi-direction hatching just from band-to-band rotation.
  if (angles.length === 1) return [angles[0]!]
  const idx = i % angles.length
  return [angles[idx]!]
}

// Synthesize a recipe for band ``i`` (of ``total``) from the operator's
// per-style knobs. Falls back to the master style's hardcoded
// ``bandRecipe`` when the knobs object is missing — keeps a freshly
// added master style without a MONO_STYLE_DEFAULTS entry rendering via
// the legacy contract.
function recipeFromKnobs(
  style: PrintStyle,
  knobs: MonoStyleKnobs | undefined,
  i: number,
  total: number,
): { algorithm: string; algorithm_options: Record<string, unknown> } | null {
  // Per-band override wins outright — operator opened the "Advanced"
  // drawer and pinned this band's options literally.
  if (knobs?.perBand && i in knobs.perBand) {
    return {
      algorithm: style.defaultAlgorithm,
      algorithm_options: { ...knobs.perBand[i] },
    }
  }
  if (!knobs) {
    return style.bandRecipe ? style.bandRecipe(i, total) : null
  }
  switch (style.id) {
    case 'pencil': {
      const angles =
        knobs.angles && knobs.angles.length > 0
          ? knobs.angles
          : ((MONO_STYLE_DEFAULTS.pencil?.angles as number[] | undefined) ?? [45, 135])
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6.5)
      return {
        algorithm: 'crosshatch',
        algorithm_options: {
          angles: pickAnglesForBand(i, total, angles),
          spacing_px: spacing,
          crossed: i === 0 && (knobs.crossed_on_darkest ?? true) && total > 1,
        },
      }
    }
    case 'halftone-shade': {
      const cell = lerp(i, total, knobs.cell_min ?? 3, knobs.cell_max ?? 9)
      return {
        algorithm: 'halftone',
        algorithm_options: { cell_size_px: cell },
      }
    }
    case 'stippling-shade': {
      // Darker bands need MORE dots → density_max applies at i=0,
      // density_min at i=total-1. Matches the legacy lerp(0.06, 0.012)
      // contract while letting the operator tune both endpoints.
      const density = lerp(i, total, knobs.density_max ?? 0.15, knobs.density_min ?? 0.012)
      return {
        algorithm: 'stippling',
        algorithm_options: {
          density,
          dot_radius_px: knobs.dot_radius ?? 0.5,
          seed: i * 7 + 13,
        },
      }
    }
    case 'engraving': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 1.8, knobs.spacing_max ?? 5)
      const wave = lerp(i, total, knobs.wave_min ?? 0.6, knobs.wave_max ?? 1.6)
      return {
        algorithm: 'scanlines',
        algorithm_options: {
          spacing_px: spacing,
          wave_amp_px: wave,
          wave_period_px: knobs.wave_period ?? 14,
        },
      }
    }
    case 'contours-topo': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      // Darker bands → more rings; rings_max at i=0, rings_min at i=total-1.
      const rings = Math.round(lerp(i, total, knobs.rings_max ?? 30, knobs.rings_min ?? 10))
      return {
        algorithm: 'contours',
        algorithm_options: { spacing_px: spacing, max_rings: rings },
      }
    }
    case 'tsp': {
      // Binary mono style: a single band, one knob (dot density). The
      // bandRecipe path is still consulted (rather than letting the
      // backend reuse a static algorithm_options) so the operator's
      // slider takes effect on /preview without /rerender.
      return {
        algorithm: 'tsp',
        algorithm_options: { density: knobs.density ?? 0.04, seed: 0 },
      }
    }
    case 'spiral-master': {
      // Tonal spiral: a single continuous spiral over the whole image
      // (one band). The wobble amplitude is modulated per pixel by the
      // backend from the luminance map; here we only ship the spiral
      // geometry knobs (turn spacing, wobble wavelength) and a 0..1
      // strength multiplier.
      return {
        algorithm: 'spiral',
        algorithm_options: {
          spacing_px: knobs.spacing_px ?? 14,
          samples_per_turn: 64,
          wavelength_px: knobs.wavelength_px ?? 10,
          tone_strength: knobs.tone_strength ?? 1,
        },
      }
    }
    case 'outline': {
      return {
        algorithm: 'edges',
        algorithm_options: { stroke_width: knobs.stroke_width ?? 0.8 },
      }
    }
    case 'centerline-trace': {
      return {
        algorithm: 'centerline',
        algorithm_options: {
          stroke_width: knobs.stroke_width ?? 0.8,
          smooth: true,
          min_branch_px: 3,
        },
      }
    }
    default:
      return style.bandRecipe ? style.bandRecipe(i, total) : null
  }
}

// Compute the synthesized algorithm_options for band ``i`` exactly as
// ``buildMonoBandRecipes`` would emit them, *ignoring* any pinned
// perBand override. Used by the "Advanced (per band)" drawer to
// pre-fill each card with the current interpolated value before the
// operator pins it.
export function interpolatedBandOptions(i: number, total: number): Record<string, unknown> {
  const style = resolveMasterStyle(_monoMasterStyleId.value)
  const knobs = _mono.value.perStyle[style.id]
  // Synthesize without consulting perBand by passing knobs minus the
  // override map.
  const interp = recipeFromKnobs(
    style,
    knobs ? { ...knobs, perBand: undefined } : undefined,
    i,
    total,
  )
  return interp?.algorithm_options ?? { ...style.defaultAlgorithmOptions }
}

/**
 * Build the per-band mono recipes for the active mono master style.
 * The bitmap composable's ``buildBandRecipes`` dispatches to this for
 * the monochrome branch; multicolour continues to live there.
 *
 * Returns ``undefined`` when the segmentation method isn't a mono one
 * (luminance_bands / thresholds) or when the active master has no
 * recipe support at all — the caller then ships no ``band_recipes``
 * field and the backend uses the static algorithm.
 */
export function buildMonoBandRecipes(
  segMethod: string,
  numBands: number,
): Array<Record<string, unknown>> | undefined {
  if (segMethod !== 'luminance_bands' && segMethod !== 'thresholds') return undefined
  const style = resolveMasterStyle(_monoMasterStyleId.value)
  if (!style.bandRecipe && !(style.id in MONO_STYLE_DEFAULTS)) return undefined
  // Binary mono modes render exactly one layer (drop_background drops
  // the lighter side of the threshold), so emit a single recipe.
  const total = segMethod === 'luminance_bands' ? numBands : 1
  const knobs = _mono.value.perStyle[style.id]
  return Array.from({ length: total }, (_, i) => {
    const recipe = recipeFromKnobs(style, knobs, i, total)
    if (!recipe) {
      return {
        algorithm: style.defaultAlgorithm,
        algorithm_options: { ...style.defaultAlgorithmOptions },
      }
    }
    return {
      algorithm: recipe.algorithm,
      algorithm_options: { ...recipe.algorithm_options },
    }
  })
}

// ---- Lifecycle helpers (consumed by ``useBitmapDraft``) ----

/**
 * Reset the mono recipe singleton to its pristine defaults. Called
 * by ``useBitmapDraft.rehydrateDraft`` before merging any persisted
 * ``last_options``.
 *
 * ``_monoPenSlot`` is operator-scoped (the active slot survives a
 * placement switch), so it isn't reset here.
 */
export function resetMonoRecipe(): void {
  _mono.value = defaultMono()
  _monoMasterStyleId.value = DEFAULT_MASTER_STYLE_ID
}

/**
 * Merge the mono fields out of a placement's ``last_options`` payload.
 * Handles the legacy single ``master_style_id`` field, the explicit
 * ``mono_master_style_id``, the ``mono_knobs`` block (perStyle merged
 * over defaults so older placements still pick up newly added
 * MONO_STYLE_DEFAULTS fields), and the belt-and-braces top-level
 * ``mono_ink_color`` fallback.
 */
export function rehydrateMonoFromOptions(opts: Record<string, unknown> | null | undefined): void {
  if (!opts || typeof opts !== 'object') return

  const persistedStyleId = opts.master_style_id
  if (typeof persistedStyleId === 'string' && persistedStyleId) {
    _monoMasterStyleId.value = persistedStyleId
  }
  // Explicit per-mode id takes precedence over the legacy single field
  // when both are present (post-multicolour-master placements always
  // ship the pair).
  const persistedMono = opts.mono_master_style_id
  if (typeof persistedMono === 'string' && persistedMono) {
    _monoMasterStyleId.value = persistedMono
  }

  // Monochrome knobs — merge over defaultMono() so a placement that
  // pre-dates a newly added style still gets its defaults populated
  // from MONO_STYLE_DEFAULTS. Persisted ink_color and per-style
  // overrides win where present.
  const monoOpts = opts.mono_knobs
  if (monoOpts && typeof monoOpts === 'object') {
    const m = monoOpts as Partial<MonoKnobsDraft>
    if (typeof m.ink_color === 'string') _mono.value.ink_color = m.ink_color
    if (m.perStyle && typeof m.perStyle === 'object') {
      for (const [styleId, knobs] of Object.entries(m.perStyle)) {
        if (knobs && typeof knobs === 'object') {
          _mono.value.perStyle[styleId] = {
            ...defaultMonoStyleKnobs(styleId),
            ...(knobs as MonoStyleKnobs),
          }
        }
      }
    }
  }
  // ``mono_ink_color`` is also accepted at the top level as a
  // belt-and-braces shortcut; mono_knobs.ink_color is the canonical
  // source but persisted older formats can drop just the top-level
  // field.
  const inkTop = opts.mono_ink_color
  if (typeof inkTop === 'string') _mono.value.ink_color = inkTop
}

/**
 * Snapshot the current mono recipe as the new committed baseline.
 * Called by ``useBitmapDraft.markCommitted``.
 */
export function markMonoCommitted(): void {
  _baselineMono.value = snap(_mono.value)
}

export const isMonoDirty: ComputedRef<boolean> = _isMonoDirty

export const monoRef: Ref<MonoKnobsDraft> = _mono
export const monoMasterStyleIdRef: Ref<string> = _monoMasterStyleId
export const monoPenSlotRef: Ref<number> = _monoPenSlot

// ---- Public composable ----
export function useMonoRecipe() {
  return {
    mono: _mono,
    monoMasterStyleId: _monoMasterStyleId,
    monoPenSlot: _monoPenSlot,
    isDirty: _isMonoDirty,
    setMonoInkColor,
    setMonoAdvancedMode,
    getMonoStyleKnobs,
    setMonoKnob,
    setMonoBandOverride,
    resetMonoStyleKnobs,
    setMonoMasterStyleId,
    interpolatedBandOptions,
    buildMonoBandRecipes,
    rehydrateFromOptions: rehydrateMonoFromOptions,
    reset: resetMonoRecipe,
    markCommitted: markMonoCommitted,
  }
}
