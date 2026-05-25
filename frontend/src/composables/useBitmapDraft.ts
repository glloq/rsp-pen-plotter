// Singleton owner of the edit modal's "what should we render" state:
//
//   - the BitmapDraft (segmentation method, palette, algorithm + knobs,
//     post-process refinements, detail level)
//   - the TypographyDraft (font, size, page geometry)
//   - the operator's mono pen-slot / master-style selection
//   - the palette-follows-installed-pens toggle
//
// Everything used to live inline at the top of SourceSection.vue. Hoisting
// it into a module-level singleton (same pattern as ``useEditState``) is
// what unlocks the 4-tab restructure: ColorsTab, RenderTab and the
// existing SourceTab all need to read/write the same bitmap object, and
// passing it via props between siblings would mean reparenting every
// card. The modal is mounted at most once at a time so a singleton is
// strictly simpler than provide/inject.
//
// Also collapses the previously-scattered ``buildOptions`` /
// ``buildSegmentationOptions`` / ``buildAlgorithmOptions`` helpers so the
// /preview scheduler and the /upload submission share the same payload
// builder.

import { computed, ref } from 'vue'
import type { SegmentationMethod } from '../api/client'
import {
  resolveMasterStyle,
  resolveMulticolorStyle,
  DEFAULT_MASTER_STYLE_ID,
  DEFAULT_MULTICOLOR_STYLE_ID,
  MONO_STYLE_DEFAULTS,
  MULTICOLOR_STYLE_DEFAULTS,
  lerp,
  type PrintStyle,
} from '../data/printRegistry'

// Photo-editor adjustments the operator can apply before segmentation.
// Mirrors ``PreprocessOptions`` on the backend; every field defaults to
// a neutral value so the payload is safe to ship unconditionally.
export type PreprocessDraft = {
  brightness: number   // -1..+1, 0 = neutral
  contrast: number     // -1..+1, 0 = neutral
  saturation: number   // 0..2, 1 = neutral
  gamma: number        // 0.1..5, 1 = neutral
  black_point: number  // 0..255
  white_point: number  // 0..255
  sharpen: number      // 0..2
  blur_px: number      // 0..10
  invert: boolean
  grayscale: boolean
  auto_contrast: boolean
  // Floyd-Steinberg error diffusion to an N-level grey ramp. 0 = off,
  // 2 = pure binary, 3..8 = the useful range for shaded mono modes
  // and for pre-clustering before kmeans (snaps gradients to discrete
  // tones, makes halftone / stippling read crisper).
  dither_levels: number
  rotate_deg: 0 | 90 | 180 | 270
  flip_h: boolean
  flip_v: boolean
  // Normalised crop rectangle [x, y, w, h] in [0, 1], or null for no crop.
  crop: [number, number, number, number] | null
}

export type BitmapDraft = {
  preprocess: PreprocessDraft
  segmentation_method: SegmentationMethod
  num_colors: number
  num_bands: number
  thresholds: number[]
  // Specific colours pinned via the "Colours" block. Non-empty switches
  // segmentation to ``fixed_palette`` (snap to exactly these colours);
  // empty falls back to kmeans for ``num_colors`` automatic colours.
  palette: string[]
  min_region_pixels: number
  merge_delta_e: number
  max_dimension_px: number
  drop_background: boolean
  background_luminance: number
  algorithm: string
  // Master styles and presets write their full options here. This dict
  // is the single source of truth for the master-style algorithm; the
  // backend reads it verbatim.
  algorithm_options: Record<string, unknown>
}

// Path-level treatment applied between the image-preprocess step and
// the colour/render stages. ``centerline_mode`` switches the active
// algorithm to ``centerline`` so the vectorisation traces medial
// skeletons rather than filled outlines — essential for schematics
// and line art. ``simplify_tolerance_mm`` is passed through to the
// /optimize endpoint as the default ``LayerOptimization.simplify_tolerance_mm``.
// ``curve_fit`` is currently a UI-only flag (no backend support yet);
// shipped as a ``coming soon`` toggle so the field is reserved.
export type CurvesDraft = {
  centerline_mode: boolean
  simplify_tolerance_mm: number
  curve_fit: boolean
}

export type TypographyDraft = {
  font: string
  font_size_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  margin_mm: number
  page_width_mm: number
  page_height_mm: number
}

export function defaultPreprocess(): PreprocessDraft {
  return {
    brightness: 0,
    contrast: 0,
    saturation: 1,
    gamma: 1,
    black_point: 0,
    white_point: 255,
    sharpen: 0,
    blur_px: 0,
    invert: false,
    grayscale: false,
    auto_contrast: false,
    dither_levels: 0,
    rotate_deg: 0,
    flip_h: false,
    flip_v: false,
    crop: null,
  }
}

// True when every preprocess field is at its neutral value; lets the UI
// display a "default" badge and the close-confirm dialog stay quiet.
export function isPreprocessNeutral(p: PreprocessDraft): boolean {
  return (
    p.brightness === 0
    && p.contrast === 0
    && p.saturation === 1
    && p.gamma === 1
    && p.black_point === 0
    && p.white_point === 255
    && p.sharpen === 0
    && p.blur_px === 0
    && !p.invert
    && !p.grayscale
    && !p.auto_contrast
    && p.dither_levels === 0
    && p.rotate_deg === 0
    && !p.flip_h
    && !p.flip_v
    && p.crop === null
  )
}

export function defaultBitmap(): BitmapDraft {
  return {
    preprocess: defaultPreprocess(),
    segmentation_method: 'kmeans',
    num_colors: 4,
    num_bands: 4,
    thresholds: [0.33, 0.66],
    palette: [],
    min_region_pixels: 0,
    merge_delta_e: 0,
    max_dimension_px: 800,
    drop_background: true,
    background_luminance: 0.92,
    algorithm: 'direct',
    algorithm_options: {},
  }
}

export function defaultCurves(): CurvesDraft {
  return {
    centerline_mode: false,
    simplify_tolerance_mm: 0.05,
    curve_fit: false,
  }
}

// Operator-tunable knobs that drive the single-pen preview. In
// monochrome mode every gray level must come from algorithm density
// (line spacing, hatch angle count, dot density, halftone cell size,
// etc.) instead of from multiple ink colours. ``ink_color`` is the
// stroke colour every layer's SVG uses; ``perStyle[id]`` carries the
// per-master-style range knobs that ``buildBandRecipes`` interpolates
// across bands.
//
// Each ``MonoStyleKnobs`` field is optional so a freshly added master
// style without a defaults entry in ``MONO_STYLE_DEFAULTS`` still
// renders via the legacy ``bandRecipe`` fallback in ``printRegistry``.
// ``perBand[i]`` is a sparse override map: present band indices skip
// interpolation and use the literal options dict instead.
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
  wave_period?: number
  dot_radius?: number
  angles?: number[]
  crossed_on_darkest?: boolean
  stroke_width?: number
  // Single-value knobs for binary styles where there's no min/max
  // gradient — TSP density and Spiral spacing each control darkness
  // via one number rather than an interpolated range.
  density?: number
  spacing_px?: number
  perBand?: Record<number, Record<string, unknown>>
}

export type MonoKnobsDraft = {
  ink_color: string
  // When true, the per-band override drawer is shown and the operator
  // can pin individual band recipes. Default false keeps the UI simple
  // for the typical operator who only needs the global range sliders.
  advanced_mode: boolean
  perStyle: Record<string, MonoStyleKnobs>
}

// Operator-tunable knobs for the multicolour master styles. Same
// shape as ``MonoStyleKnobs`` but only the fields each multicolour
// recipe actually reads (no angle chips, no per-band override drawer
// — multicolour clusters aren't ordered by darkness in a way that
// would make pinning the i-th cluster meaningful without exposing the
// cluster's source colour first).
export type MulticolorStyleKnobs = {
  spacing_min?: number
  spacing_max?: number
  density_min?: number
  density_max?: number
  rings_min?: number
  rings_max?: number
  amp_min?: number
  amp_max?: number
  seed_spacing_min?: number
  seed_spacing_max?: number
  dot_radius?: number
  iterations?: number
  cell_size?: number
  angle_step?: number
  crossed?: boolean
  step_px?: number
  max_steps?: number
  noise_scale?: number
  bidirectional?: boolean
  period_px?: number
  jitter?: number
  max_rings?: number
  // Knobs shared by the second-wave colour masters (edges, centerline,
  // spiral-classic, scanlines, tsp / tsp_opt, hilbert, gosper, eulerian
  // hatch). Each keeps the same naming as its mono counterpart so the
  // params card stays readable when the cards share sliders.
  stroke_width?: number
  min_branch_px?: number
  samples_per_turn?: number
  wave_amp_px?: number
  wave_period_px?: number
  min_run_px?: number
  order?: number
  max_points?: number
  time_budget_s?: number
}

export type MulticolorKnobsDraft = {
  perStyle: Record<string, MulticolorStyleKnobs>
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

export function defaultMulticolorStyleKnobs(styleId: string): MulticolorStyleKnobs {
  const src = MULTICOLOR_STYLE_DEFAULTS[styleId] ?? {}
  return { ...(src as MulticolorStyleKnobs) }
}

export function defaultMulticolor(): MulticolorKnobsDraft {
  const perStyle: Record<string, MulticolorStyleKnobs> = {}
  for (const id of Object.keys(MULTICOLOR_STYLE_DEFAULTS)) {
    perStyle[id] = defaultMulticolorStyleKnobs(id)
  }
  return { perStyle }
}

export function defaultTypography(): TypographyDraft {
  return {
    font: 'futural',
    font_size_mm: 4.0,
    line_spacing: 1.5,
    alignment: 'left',
    stroke_width_mm: 0.3,
    margin_mm: 15.0,
    page_width_mm: 210.0,
    page_height_mm: 297.0,
  }
}

// ---- Singleton state ----
const _bitmap = ref<BitmapDraft>(defaultBitmap())
const _curves = ref<CurvesDraft>(defaultCurves())
const _typo = ref<TypographyDraft>(defaultTypography())
const _monoPenSlot = ref<number>(0)
const _monoMasterStyleId = ref<string>(DEFAULT_MASTER_STYLE_ID)
const _multicolorMasterStyleId = ref<string>(DEFAULT_MULTICOLOR_STYLE_ID)
const _mono = ref<MonoKnobsDraft>(defaultMono())
const _multicolor = ref<MulticolorKnobsDraft>(defaultMulticolor())
const _paletteFollowsPens = ref<boolean>(true)

// Tracks the segmentation knobs the operator manually changed since the
// last preset/print-mode application. Used by ``setSegmentationFromStyle``
// to warn (via toast) when an automatic action — switching master style,
// flipping print mode, toggling palette-follows-pens — is about to
// overwrite a manual choice the operator made on the SvgTab or
// MasterStyleParams. Reset on placement rehydrate and on intentional
// "reset to preset" calls (force=true).
type SegmentationField = 'method' | 'num_bands' | 'thresholds' | 'drop_background' | 'background_luminance'
const _segmentationTouched = ref<Set<SegmentationField>>(new Set())

// "Was this draft committed yet?" — set to false when SourceSection
// rehydrates on a placement switch and flipped to true after /upload.
// Phase 4's dirty-tracker will hang off this in addition to a snapshot.
const _committed = ref<boolean>(false)

// ---- Computed views ----
// Print mode is derived from the segmentation method + master-style id
// so the toggle stays in sync with whatever the operator picked in the
// segmentation block. ``thresholds with one entry & active master is
// binary`` is the only path where ``thresholds`` means "monochrome
// binary mode" instead of a generic 1-cut multicolour split.
const _printMode = computed<'multicolor' | 'monochrome'>(() => {
  if (_bitmap.value.segmentation_method === 'luminance_bands') return 'monochrome'
  const masterStyle = resolveMasterStyle(_monoMasterStyleId.value)
  if (
    masterStyle.segmentation?.method === 'thresholds'
    && _bitmap.value.segmentation_method === 'thresholds'
    && _bitmap.value.thresholds.length === 1
  ) {
    return 'monochrome'
  }
  return 'multicolor'
})

// ---- Mutators ----

// Resets every draft to its default, then overlays any options the
// placement was actually uploaded with — so reopening the modal on an
// already-converted file shows the parameters that produced it instead
// of a fresh-defaults form that would silently desync from the
// committed SVG on the next /preview.
//
// ``placement`` shape mirrors what ``store.selectedPlacement`` returns;
// kept loose so this composable doesn't import the pinia store.
export interface PlacementLike {
  last_options?: Record<string, unknown> | null
  source_file?: string | null
}

export interface RehydrateContext {
  placement: PlacementLike | null | undefined
  // Installed pen colours from the active machine profile — used to
  // infer ``paletteFollowsPens`` from the persisted palette.
  installedPenColors: string[]
}

export function rehydrateDraft(ctx: RehydrateContext): void {
  _bitmap.value = defaultBitmap()
  _curves.value = defaultCurves()
  _typo.value = defaultTypography()
  _paletteFollowsPens.value = true
  _committed.value = false
  // Reset the master-style id so a stale value from a previous
  // placement can't keep feeding the wrong ``bandRecipe`` into
  // ``/preview``. The actual id (if the placement was persisted with
  // one) is read back from ``last_options.master_style_id`` below.
  // Without this reset, opening the modal on a placement saved with
  // Halftone after editing a Pencil one would keep generating Pencil
  // recipes for every /preview round-trip even though the operator
  // never sees ``pencil`` highlighted in the picker.
  _monoMasterStyleId.value = DEFAULT_MASTER_STYLE_ID
  _multicolorMasterStyleId.value = DEFAULT_MULTICOLOR_STYLE_ID
  _mono.value = defaultMono()
  _multicolor.value = defaultMulticolor()
  // Rehydrating wipes the touched tracker — the persisted last_options
  // ARE the baseline, so subsequent style switches shouldn't think the
  // operator has been hand-tweaking.
  _segmentationTouched.value = new Set()

  const opts = ctx.placement?.last_options
  if (!opts || typeof opts !== 'object') return

  const target = _bitmap.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key === 'preprocess') continue // handled below as a partial merge
    if (key in opts) target[key] = opts[key]
  }
  // Merge persisted preprocess fields over the neutral defaults so an
  // older placement (no ``preprocess`` block, or one missing some
  // recently-added fields) still produces an identical render.
  const preprocessOpts = (opts as Record<string, unknown>).preprocess
  if (preprocessOpts && typeof preprocessOpts === 'object') {
    const fresh = defaultPreprocess() as Record<string, unknown>
    for (const key of Object.keys(fresh)) {
      if (key in (preprocessOpts as Record<string, unknown>)) {
        fresh[key] = (preprocessOpts as Record<string, unknown>)[key]
      }
    }
    _bitmap.value.preprocess = fresh as unknown as PreprocessDraft
  }
  // Restore the master-style id when the placement was committed with
  // one. Falls back to the default if the field is missing (older
  // placements predate the field) or unparseable.
  const persistedStyleId = (opts as Record<string, unknown>).master_style_id
  if (typeof persistedStyleId === 'string' && persistedStyleId) {
    _monoMasterStyleId.value = persistedStyleId
  }
  // Explicit per-mode ids take precedence over the legacy single field
  // when both are present (post-multicolour-master placements always
  // ship the pair).
  const persistedMono = (opts as Record<string, unknown>).mono_master_style_id
  if (typeof persistedMono === 'string' && persistedMono) {
    _monoMasterStyleId.value = persistedMono
  }
  const persistedMulti = (opts as Record<string, unknown>).multicolor_master_style_id
  if (typeof persistedMulti === 'string' && persistedMulti) {
    _multicolorMasterStyleId.value = persistedMulti
  }
  // algorithm_options is the single source of truth — already merged
  // by the generic key loop above. The legacy "scattered per-algo
  // fields" the rehydrate path used to mirror are gone; nothing in the
  // UI reads them. Pre-migration placements still round-trip cleanly:
  // their algorithm_options dict is preserved verbatim.
  const segOpts = (opts as Record<string, unknown>).segmentation_options as
    | Record<string, unknown>
    | undefined
  if (segOpts && 'palette' in segOpts && Array.isArray(segOpts.palette)) {
    _bitmap.value.palette = [...(segOpts.palette as string[])]
    const sameAsPens
      = _bitmap.value.palette.length === ctx.installedPenColors.length
      && _bitmap.value.palette.every((c, i) => c === ctx.installedPenColors[i])
    _paletteFollowsPens.value = sameAsPens
  }
  const typoTarget = _typo.value as Record<string, unknown>
  for (const key of Object.keys(typoTarget)) {
    if (key in opts) typoTarget[key] = opts[key]
  }
  const curvesOpts = (opts as Record<string, unknown>).curves
  if (curvesOpts && typeof curvesOpts === 'object') {
    const fresh = defaultCurves() as Record<string, unknown>
    for (const key of Object.keys(fresh)) {
      if (key in (curvesOpts as Record<string, unknown>)) {
        fresh[key] = (curvesOpts as Record<string, unknown>)[key]
      }
    }
    _curves.value = fresh as unknown as CurvesDraft
  }
  // Monochrome knobs — merge over defaultMono() so a placement that
  // pre-dates a newly added style still gets its defaults populated
  // from MONO_STYLE_DEFAULTS. Persisted ink_color and per-style
  // overrides win where present.
  const monoOpts = (opts as Record<string, unknown>).mono_knobs
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
  const inkTop = (opts as Record<string, unknown>).mono_ink_color
  if (typeof inkTop === 'string') _mono.value.ink_color = inkTop
  // Multicolour knobs — same merge shape as mono so a placement
  // committed before a freshly added field still hydrates cleanly.
  const multiOpts = (opts as Record<string, unknown>).multicolor_knobs
  if (multiOpts && typeof multiOpts === 'object') {
    const m = multiOpts as Partial<MulticolorKnobsDraft>
    if (m.perStyle && typeof m.perStyle === 'object') {
      for (const [styleId, knobs] of Object.entries(m.perStyle)) {
        if (knobs && typeof knobs === 'object') {
          _multicolor.value.perStyle[styleId] = {
            ...defaultMulticolorStyleKnobs(styleId),
            ...(knobs as MulticolorStyleKnobs),
          }
        }
      }
    }
  }
  // A placement that round-tripped through /upload is by definition
  // committed; we only flip back to dirty on the first user mutation
  // (handled by Phase 4's useDirtyTracker — for now we treat it as
  // committed so the Apply button defaults to the right state).
  _committed.value = true
}

// Apply a saved preset (from ``store.presets``) onto the draft. Same
// shape as ``rehydrateDraft`` but takes the options dict directly.
export function applyPresetOptions(opts: Record<string, unknown>): void {
  const target = _bitmap.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key in opts) target[key] = opts[key]
  }
}

// Mark a segmentation field as manually changed by the operator. Called
// by the SvgTab's SegmentationMethodCard, MasterStyleParams sliders and
// PaletteCard whenever a user-driven mutation lands. The next automatic
// action that would overwrite a touched field surfaces a warning toast
// instead of clobbering silently. SegmentationMethodCard / MasterStyleParams
// / PaletteCard call this directly; programmatic mutators (this module's
// own ``setSegmentationFromStyle``) bypass it.
export function markSegmentationTouched(...fields: SegmentationField[]): void {
  if (!fields.length) return
  const next = new Set(_segmentationTouched.value)
  for (const f of fields) next.add(f)
  _segmentationTouched.value = next
}

// Per-style segmentation rewrite, centralised so ``setPrintMode`` and
// ``setMasterStyle`` (the StyleTab picker) share one path. Returns the
// list of touched fields that were about to be overwritten — empty when
// the change is harmless, populated when the caller should warn the
// operator. ``force`` skips the warning entirely (used by intentional
// reset paths like rehydrate or a fresh placement).
function applyStyleSegmentation(
  style: PrintStyle,
  opts: { force?: boolean } = {},
): SegmentationField[] {
  const seg = style.segmentation
  if (!seg) return []
  const b = _bitmap.value
  const wouldOverwrite: SegmentationField[] = []
  if (!opts.force) {
    if (
      _segmentationTouched.value.has('method')
      && b.segmentation_method !== seg.method
    ) wouldOverwrite.push('method')
    if (
      _segmentationTouched.value.has('drop_background')
      && b.drop_background !== seg.drop_background
    ) wouldOverwrite.push('drop_background')
    if (
      _segmentationTouched.value.has('background_luminance')
      && b.background_luminance !== seg.background_luminance
    ) wouldOverwrite.push('background_luminance')
    if (
      seg.method === 'luminance_bands'
      && _segmentationTouched.value.has('num_bands')
    ) {
      const target = seg.default_num_bands ?? 4
      if (b.num_bands !== target && (b.num_bands < 2 || b.num_bands > 6)) {
        wouldOverwrite.push('num_bands')
      }
    }
    if (
      seg.method === 'thresholds'
      && _segmentationTouched.value.has('thresholds')
    ) {
      const target = seg.default_threshold ?? 0.5
      const current = b.thresholds[0] ?? target
      if (b.thresholds.length !== 1 || Math.abs(current - target) > 1e-6) {
        wouldOverwrite.push('thresholds')
      }
    }
  }

  b.segmentation_method = seg.method
  b.drop_background = seg.drop_background
  b.background_luminance = seg.background_luminance
  b.algorithm = style.defaultAlgorithm
  b.algorithm_options = { ...style.defaultAlgorithmOptions }
  if (seg.method === 'luminance_bands') {
    if (b.num_bands < 2 || b.num_bands > 6) {
      b.num_bands = seg.default_num_bands ?? 4
    }
  } else if (seg.method === 'thresholds') {
    b.thresholds = [seg.default_threshold ?? 0.5]
  } else if (seg.method === 'kmeans') {
    // Multicolour master styles carry a default cluster count that the
    // operator can still override via the colour-mode num_colors slider.
    // Only stomp num_colors when the operator hasn't touched it recently
    // (out-of-range or first-time application).
    const target = seg.default_num_colors ?? 4
    if (b.num_colors < 1 || b.num_colors > 16) {
      b.num_colors = target
    }
  }
  // Style picker / print-mode flip resets the touched set: this is the
  // new baseline.
  _segmentationTouched.value = new Set()
  return wouldOverwrite
}

// Switch between multicolour and monochrome. Rewrites the segmentation
// method, algorithm and post-process knobs to the active master style's
// recipe (mono) or back to a sensible kmeans default (multi). Returns
// the list of fields the operator had manually touched and that this
// call overwrote; callers may surface a toast.
// ---- Monochrome knob mutators ----
// Setters keep the live draft and the dirty-tracker in sync; UI
// components import these instead of mutating ``_mono`` directly so
// future side-effects (e.g. emitting an analytics event when angles
// change) have one place to land.
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
  return _mono.value.perStyle[styleId]
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
    knobs.perBand[bandIndex] = { ...override }
  }
}

export function resetMonoStyleKnobs(styleId: string): void {
  _mono.value.perStyle[styleId] = defaultMonoStyleKnobs(styleId)
}

// Multicolour twins of the mono knob mutators. Symmetric API so the
// shared params components can use the same setter pattern regardless
// of print mode.
export function getMulticolorStyleKnobs(styleId: string): MulticolorStyleKnobs {
  if (!_multicolor.value.perStyle[styleId]) {
    _multicolor.value.perStyle[styleId] = defaultMulticolorStyleKnobs(styleId)
  }
  return _multicolor.value.perStyle[styleId]
}

export function setMulticolorKnob<K extends keyof MulticolorStyleKnobs>(
  styleId: string,
  key: K,
  value: MulticolorStyleKnobs[K],
): void {
  const knobs = getMulticolorStyleKnobs(styleId)
  knobs[key] = value
}

export function resetMulticolorStyleKnobs(styleId: string): void {
  _multicolor.value.perStyle[styleId] = defaultMulticolorStyleKnobs(styleId)
}

export function setPrintMode(
  mode: 'multicolor' | 'monochrome',
  opts: { force?: boolean } = {},
): SegmentationField[] {
  if (mode === 'monochrome') {
    const style = resolveMasterStyle(_monoMasterStyleId.value)
    const overwritten = applyStyleSegmentation(style, opts)
    // Clear the multicolour palette so a stale ``fixed_palette`` from
    // the previous mode can't keep the preview / upload painting in
    // colour. Without this, switching multi → mono left the operator
    // with N coloured layers because ``buildSegmentationOptions`` would
    // still serve the old palette if anything tipped the
    // segmentation_method back to fixed_palette.
    _bitmap.value.palette = []
    _paletteFollowsPens.value = false
    return overwritten
  }
  // Multicolour: apply the active multicolour master style so the
  // segmentation method, num_colors, default algorithm and per-cluster
  // recipe all line up with the operator's chosen preset. Same code
  // path as monochrome, just resolved from the multicolour family.
  const style = resolveMulticolorStyle(_multicolorMasterStyleId.value)
  const overwritten = applyStyleSegmentation(style, opts)
  _paletteFollowsPens.value = true
  return overwritten
}

// Switch master style. Returns the list of touched fields overwritten
// (callers surface a toast). Mirrors setPrintMode's signature so the
// StyleTab can share the warning code path. Caller is still
// responsible for the post-upload ``applyMasterStyleToLayers`` push.
export function setMasterStyle(
  id: string,
  opts: { force?: boolean } = {},
): SegmentationField[] {
  _monoMasterStyleId.value = id
  return applyStyleSegmentation(resolveMasterStyle(id), opts)
}

// Multicolour twin of ``setMasterStyle``. Stores the active multicolour
// master id and rewrites the segmentation / default algorithm exactly
// the same way the mono path does — picker UX stays symmetric and the
// returned touched-field list flows into the same toast machinery.
export function setMulticolorMasterStyle(
  id: string,
  opts: { force?: boolean } = {},
): SegmentationField[] {
  _multicolorMasterStyleId.value = id
  return applyStyleSegmentation(resolveMulticolorStyle(id), opts)
}

// ---- Payload builders ----

export function buildSegmentationOptions(): Record<string, unknown> {
  const b = _bitmap.value
  if (b.segmentation_method === 'luminance_bands') return { num_bands: b.num_bands }
  if (b.segmentation_method === 'thresholds') return { levels: b.thresholds }
  if (b.segmentation_method === 'fixed_palette') return { palette: b.palette }
  return {}
}

export function buildAlgorithmOptions(): Record<string, unknown> {
  return { ..._bitmap.value.algorithm_options }
}

// Pick the i-th angle for a pencil-style band, cycling through the
// operator's chosen angle list. ``angles`` must be non-empty; callers
// guarantee this by falling back to MONO_STYLE_DEFAULTS.pencil.angles
// when the operator clears the list.
function pickAnglesForBand(
  i: number,
  _total: number,
  angles: number[],
): number[] {
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
      const angles = knobs.angles && knobs.angles.length > 0
        ? knobs.angles
        : ((MONO_STYLE_DEFAULTS.pencil?.angles as number[] | undefined) ?? [45, 135])
      const spacing = lerp(
        i, total,
        knobs.spacing_min ?? 2.5,
        knobs.spacing_max ?? 6.5,
      )
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
      const cell = lerp(
        i, total,
        knobs.cell_min ?? 3,
        knobs.cell_max ?? 9,
      )
      return {
        algorithm: 'halftone',
        algorithm_options: { cell_size_px: cell },
      }
    }
    case 'stippling-shade': {
      // Darker bands need MORE dots → density_max applies at i=0,
      // density_min at i=total-1. Matches the legacy lerp(0.06, 0.012)
      // contract while letting the operator tune both endpoints.
      const density = lerp(
        i, total,
        knobs.density_max ?? 0.06,
        knobs.density_min ?? 0.012,
      )
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
      const spacing = lerp(
        i, total,
        knobs.spacing_min ?? 1.8,
        knobs.spacing_max ?? 5,
      )
      const wave = lerp(
        i, total,
        knobs.wave_min ?? 0.6,
        knobs.wave_max ?? 1.6,
      )
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
      const spacing = lerp(
        i, total,
        knobs.spacing_min ?? 2.5,
        knobs.spacing_max ?? 6,
      )
      // Darker bands → more rings; rings_max at i=0, rings_min at i=total-1.
      const rings = Math.round(lerp(
        i, total,
        knobs.rings_max ?? 30,
        knobs.rings_min ?? 10,
      ))
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
      // Same single-band shape as TSP: spacing_px is the only darkness
      // lever, fed through the recipe so the slider edit re-fires
      // /preview with the new value.
      return {
        algorithm: 'spiral',
        algorithm_options: {
          spacing_px: knobs.spacing_px ?? 3,
          samples_per_turn: 64,
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
// ``buildBandRecipes`` would emit them, *ignoring* any pinned perBand
// override. Used by the "Advanced (per band)" drawer to pre-fill each
// card with the current interpolated value before the operator pins it.
export function interpolatedBandOptions(
  i: number,
  total: number,
): Record<string, unknown> {
  const style = resolveMasterStyle(_monoMasterStyleId.value)
  const knobs = _mono.value.perStyle[style.id]
  // Synthesize without consulting perBand by passing knobs minus the
  // override map.
  const interp = recipeFromKnobs(
    style,
    knobs ? { ...knobs, perBand: undefined } : undefined,
    i, total,
  )
  return interp?.algorithm_options ?? { ...style.defaultAlgorithmOptions }
}

// Build the per-band recipes for the current master style so the
// backend's /preview applies them inline instead of just the uniform
// algorithm. Emitted in mono shaded mode (luminance_bands → N recipes)
// AND in mono binary mode (thresholds → 1 recipe), so single-band
// styles like TSP / Spiral / Outline / Centerline pick up the
// operator's global slider edits on /preview without requiring a
// /rerender round-trip.
function buildBandRecipes(): Array<Record<string, unknown>> | undefined {
  if (_printMode.value === 'monochrome') {
    const segMethod = _bitmap.value.segmentation_method
    if (segMethod !== 'luminance_bands' && segMethod !== 'thresholds') return undefined
    const style = resolveMasterStyle(_monoMasterStyleId.value)
    if (!style.bandRecipe && !(style.id in MONO_STYLE_DEFAULTS)) return undefined
    // Binary mono modes render exactly one layer (drop_background drops
    // the lighter side of the threshold), so emit a single recipe.
    const total = segMethod === 'luminance_bands'
      ? _bitmap.value.num_bands
      : 1
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
  // Multicolour: expand the active multicolour master's ``colorRecipe``
  // across the segmentation's predicted cluster count. The backend's
  // existing band_recipes plumbing handles both modes — recipes are
  // matched by cluster order (darkest first) regardless of segmentation
  // method, so the same payload field carries both kinds of overrides.
  const style = resolveMulticolorStyle(_multicolorMasterStyleId.value)
  if (!style.colorRecipe && !(style.id in MULTICOLOR_STYLE_DEFAULTS)) return undefined
  const b = _bitmap.value
  // For kmeans the cluster count is num_colors; for fixed_palette it's
  // the palette length. luminance_bands / thresholds aren't valid
  // multicolour segmentations, so they only show up if the operator
  // hand-picked a method that doesn't match the master — fall through
  // to a sensible default in that case.
  let total = 4
  if (b.segmentation_method === 'kmeans') total = b.num_colors
  else if (b.segmentation_method === 'fixed_palette') total = b.palette.length
  if (total < 1) return undefined
  const knobs = _multicolor.value.perStyle[style.id]
  return Array.from({ length: total }, (_, i) => {
    const grey = Math.round(255 * (i / Math.max(1, total - 1)))
    const hexFallback = `#${grey.toString(16).padStart(2, '0').repeat(3)}`
    const recipe = colorRecipeFromKnobs(style, knobs, i, total, hexFallback)
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

// Synthesize a recipe for cluster ``i`` (of ``total``) from the
// operator's per-style multicolour knobs. Falls back to the registry's
// hardcoded ``colorRecipe`` when the knobs object is missing — keeps a
// freshly-added multicolour master without a MULTICOLOR_STYLE_DEFAULTS
// entry rendering via the legacy contract.
function colorRecipeFromKnobs(
  style: PrintStyle,
  knobs: MulticolorStyleKnobs | undefined,
  i: number,
  total: number,
  hex: string,
): { algorithm: string; algorithm_options: Record<string, unknown> } | null {
  if (!knobs) {
    return style.colorRecipe ? style.colorRecipe(i, total, hex) : null
  }
  switch (style.id) {
    case 'color-flat':
      return { algorithm: 'direct', algorithm_options: {} }
    case 'color-crosshatch': {
      const baseAngles = [0, 45, 90, 135, 30, 75, 120, 165]
      const step = knobs.angle_step ?? 45
      const angle = (i * step + (baseAngles[i % baseAngles.length] ?? 0)) % 180
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      return {
        algorithm: 'crosshatch',
        algorithm_options: {
          angle_deg: angle,
          spacing_px: spacing,
          crossed: knobs.crossed ?? false,
        },
      }
    }
    case 'color-stipple': {
      // Darker clusters first → density_max at i=0, density_min at the
      // lightest cluster. Mirrors the mono ``stippling-shade`` recipe so
      // the slider direction is consistent between modes.
      const density = lerp(
        i, total,
        knobs.density_max ?? 0.05,
        knobs.density_min ?? 0.012,
      )
      return {
        algorithm: 'voronoi_stipple',
        algorithm_options: {
          density,
          dot_radius_px: knobs.dot_radius ?? 0.5,
          iterations: knobs.iterations ?? 4,
          seed: i * 13 + 7,
        },
      }
    }
    case 'color-halftone-cmyk': {
      const r = parseInt(hex.slice(1, 3), 16) / 255
      const g = parseInt(hex.slice(3, 5), 16) / 255
      const bch = parseInt(hex.slice(5, 7), 16) / 255
      const c = 1 - r, m = 1 - g, y = 1 - bch
      let angle = 45
      const max = Math.max(c, m, y)
      if (max > 0.15) {
        if (max === c) angle = 15
        else if (max === m) angle = 75
        else angle = 0
      }
      return {
        algorithm: 'halftone',
        algorithm_options: {
          cell_size_px: knobs.cell_size ?? 5,
          angle_deg: angle,
        },
      }
    }
    case 'color-contours-topo': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      // Darker clusters get more rings.
      const rings = Math.round(lerp(
        i, total,
        knobs.rings_max ?? 30,
        knobs.rings_min ?? 10,
      ))
      return {
        algorithm: 'contours',
        algorithm_options: { spacing_px: spacing, max_rings: rings },
      }
    }
    case 'color-flowfield': {
      const seedSpacing = lerp(
        i, total,
        knobs.seed_spacing_min ?? 6,
        knobs.seed_spacing_max ?? 12,
      )
      return {
        algorithm: 'flowfield',
        algorithm_options: {
          seed_spacing_px: seedSpacing,
          step_px: knobs.step_px ?? 0.8,
          max_steps: knobs.max_steps ?? 600,
          bidirectional: knobs.bidirectional ?? true,
          noise_scale: knobs.noise_scale ?? 48,
          mode: 'gradient',
          seed: i * 31 + 11,
        },
      }
    }
    case 'color-sketch': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 3, knobs.spacing_max ?? 6)
      const amp = lerp(i, total, knobs.amp_max ?? 1.8, knobs.amp_min ?? 0.6)
      return {
        algorithm: 'squiggle',
        algorithm_options: {
          spacing_px: spacing,
          amp_px: amp,
          period_px: knobs.period_px ?? 8,
          jitter: knobs.jitter ?? 0.45,
          mode: 'modulated',
          seed: i * 17 + 23,
        },
      }
    }
    case 'color-spiral': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2, knobs.spacing_max ?? 5)
      return {
        algorithm: 'concentric_offset',
        algorithm_options: {
          spacing_px: spacing,
          max_rings: knobs.max_rings ?? 40,
          bridge: true,
        },
      }
    }
    case 'color-stippling-classic': {
      const density = lerp(
        i, total,
        knobs.density_max ?? 0.05,
        knobs.density_min ?? 0.012,
      )
      return {
        algorithm: 'stippling',
        algorithm_options: {
          density,
          dot_radius_px: knobs.dot_radius ?? 0.5,
          seed: i * 7 + 13,
        },
      }
    }
    case 'color-edges': {
      return {
        algorithm: 'edges',
        algorithm_options: { stroke_width: knobs.stroke_width ?? 0.8 },
      }
    }
    case 'color-centerline': {
      return {
        algorithm: 'centerline',
        algorithm_options: {
          stroke_width: knobs.stroke_width ?? 0.8,
          smooth: true,
          min_branch_px: knobs.min_branch_px ?? 3,
        },
      }
    }
    case 'color-spiral-classic': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2, knobs.spacing_max ?? 5)
      return {
        algorithm: 'spiral',
        algorithm_options: {
          spacing_px: spacing,
          samples_per_turn: knobs.samples_per_turn ?? 64,
        },
      }
    }
    case 'color-scanlines': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      return {
        algorithm: 'scanlines',
        algorithm_options: {
          spacing_px: spacing,
          wave_amp_px: knobs.wave_amp_px ?? 0,
          wave_period_px: knobs.wave_period_px ?? 12,
        },
      }
    }
    case 'color-tsp': {
      const density = lerp(
        i, total,
        knobs.density_max ?? 0.05,
        knobs.density_min ?? 0.012,
      )
      return {
        algorithm: 'tsp',
        algorithm_options: { density, seed: i * 11 + 5 },
      }
    }
    case 'color-hilbert': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      return {
        algorithm: 'hilbert',
        algorithm_options: {
          spacing_px: spacing,
          min_run_px: knobs.min_run_px ?? 3,
        },
      }
    }
    case 'color-gosper': {
      const spacing = lerp(i, total, knobs.spacing_min ?? 3, knobs.spacing_max ?? 5)
      return {
        algorithm: 'gosper',
        algorithm_options: {
          order: knobs.order ?? 4,
          spacing_px: spacing,
          rotation_deg: (i * 30) % 360,
        },
      }
    }
    case 'color-eulerian': {
      const baseAngles = [0, 45, 90, 135, 30, 75, 120, 165]
      const step = knobs.angle_step ?? 45
      const angle = (i * step + (baseAngles[i % baseAngles.length] ?? 0)) % 180
      const spacing = lerp(i, total, knobs.spacing_min ?? 2.5, knobs.spacing_max ?? 6)
      return {
        algorithm: 'eulerian_hatch',
        algorithm_options: {
          spacing_px: spacing,
          angle_deg: angle,
          crossed: knobs.crossed ?? false,
        },
      }
    }
    case 'color-tsp-opt': {
      const density = lerp(
        i, total,
        knobs.density_max ?? 0.05,
        knobs.density_min ?? 0.012,
      )
      return {
        algorithm: 'tsp_opt',
        algorithm_options: {
          density,
          max_points: knobs.max_points ?? 4000,
          time_budget_s: knobs.time_budget_s ?? 1.5,
          poisson_disk: true,
          seed: i * 19 + 3,
        },
      }
    }
    default:
      return style.colorRecipe ? style.colorRecipe(i, total, hex) : null
  }
}

export function buildBitmapOptions(): Record<string, unknown> {
  const b = _bitmap.value
  const c = _curves.value
  // Centerline mode (Courbes tab) overrides whichever algorithm + per-
  // band recipe the master style picked: tracing a medial skeleton makes
  // sense regardless of what the operator originally selected, and it's
  // a single global flag rather than a per-band concern.
  const algo = c.centerline_mode ? 'centerline' : b.algorithm
  const algoOpts = c.centerline_mode
    ? { stroke_width: 0.8, smooth: true, min_branch_px: 3 }
    : buildAlgorithmOptions()
  // num_colors only feeds the kmeans fallback; in mono / luminance_bands
  // / thresholds / fixed_palette modes the backend reads num_bands /
  // levels / palette and ignores num_colors. Skipping it keeps the
  // payload truthful and avoids future confusion when a backend
  // validation tightens unknown-field handling.
  const shipsNumColors
    = _printMode.value === 'multicolor' && b.segmentation_method === 'kmeans'
  const payload: Record<string, unknown> = {
    algorithm: algo,
    ...(shipsNumColors ? { num_colors: b.num_colors } : {}),
    max_dimension_px: b.max_dimension_px,
    drop_background: b.drop_background,
    background_luminance: b.background_luminance,
    segmentation_method: b.segmentation_method,
    segmentation_options: buildSegmentationOptions(),
    min_region_pixels: b.min_region_pixels,
    merge_delta_e: b.merge_delta_e,
    algorithm_options: algoOpts,
    // Photo-editor adjustments applied before downscale + segmentation.
    // Always shipped so the operator's tweaks survive /preview <->
    // /upload round-trips; neutral defaults are a no-op server-side.
    preprocess: { ...b.preprocess },
    // Persisted alongside the rest of the options so the next modal
    // open on this placement can rehydrate the same master style the
    // operator committed with. The backend tolerates unknown extras
    // (BitmapOptions ignores unrecognised keys); only the frontend
    // rehydrate path reads it back.
    master_style_id: _printMode.value === 'monochrome'
      ? _monoMasterStyleId.value
      : _multicolorMasterStyleId.value,
    // Both ids are persisted unconditionally so flipping print mode on
    // a rehydrated placement restores the operator's last choice in
    // each family (instead of resetting to the default).
    mono_master_style_id: _monoMasterStyleId.value,
    multicolor_master_style_id: _multicolorMasterStyleId.value,
    // Curves tab state — also a backend-unknown extra, read back by
    // ``rehydrateDraft`` so the toggles survive a round-trip.
    curves: { ...c },
    // Operator-tunable monochrome knobs (ink colour, per-style ranges,
    // per-band overrides). Backend ignores the field; the frontend
    // rehydrate path reads it back. Deep clone so persisted snapshots
    // don't share refs with the live draft.
    mono_knobs: JSON.parse(JSON.stringify(_mono.value)) as MonoKnobsDraft,
    // Multicolour knob set — same persistence contract as ``mono_knobs``.
    // Backend ignores the field; the frontend rehydrate path reads it
    // back so per-style range sliders survive a round-trip.
    multicolor_knobs: JSON.parse(JSON.stringify(_multicolor.value)) as MulticolorKnobsDraft,
  }
  // Only ship ``mono_ink_color`` in monochrome mode; multicolor keeps
  // its per-cluster palette colours.
  if (_printMode.value === 'monochrome') {
    payload.mono_ink_color = _mono.value.ink_color
  }
  if (c.centerline_mode) {
    // Suppress per-band variations so every layer renders as a single-
    // stroke skeleton instead of inheriting the master's crosshatch /
    // halftone recipe.
  } else {
    const bandRecipes = buildBandRecipes()
    if (bandRecipes) payload.band_recipes = bandRecipes
  }
  return payload
}

export function buildTypographyOptions(): Record<string, unknown> {
  return { ..._typo.value }
}

// Predicted number of layers the next /upload will produce. Drives the
// inline "→ N calques" badges next to the sliders that change it
// (bands, num_colors, palette length). Keeps the operator from
// having to commit and then count cards in the Layers tab to
// understand the cost of a tweak.
const _expectedLayerCount = computed<number>(() => {
  const b = _bitmap.value
  if (_printMode.value === 'monochrome') {
    if (b.segmentation_method === 'luminance_bands') return b.num_bands
    if (b.segmentation_method === 'thresholds') {
      // drop_background removes the lightest band, so N thresholds
      // produce N rendered layers. Binary mono modes ship a single
      // threshold → 1 layer.
      return b.thresholds.length
    }
    return 1
  }
  if (b.segmentation_method === 'fixed_palette') return b.palette.length
  return b.num_colors
})

// ---- Dirty tracking ----
// Snapshot of "what we last committed" — set by ``markCommitted`` after
// a successful /upload and by ``rehydrateDraft`` when loading an
// existing placement. Compared against the live drafts in
// ``isDirty`` so the UI can warn before close + disable Apply when
// nothing has drifted.
const _baselineBitmap = ref<string>('')
const _baselineTypo = ref<string>('')

function snap(value: unknown): string {
  try { return JSON.stringify(value) } catch { return '' }
}

const _baselineCurves = ref<string>('')
const _baselineMono = ref<string>('')
const _baselineMulticolor = ref<string>('')

const _isDirty = computed<boolean>(() => {
  return snap(_bitmap.value) !== _baselineBitmap.value
    || snap(_typo.value) !== _baselineTypo.value
    || snap(_curves.value) !== _baselineCurves.value
    || snap(_mono.value) !== _baselineMono.value
    || snap(_multicolor.value) !== _baselineMulticolor.value
})

function markCommitted(): void {
  _baselineBitmap.value = snap(_bitmap.value)
  _baselineTypo.value = snap(_typo.value)
  _baselineCurves.value = snap(_curves.value)
  _baselineMono.value = snap(_mono.value)
  _baselineMulticolor.value = snap(_multicolor.value)
  _committed.value = true
}

// Wired into ``rehydrateDraft`` so a loaded placement starts clean.
// Only marks the rehydrated state as the committed baseline when the
// placement actually carries committed options (``last_options``); for
// a fresh / empty placement we leave the baseline as-is so the dirty
// tracker correctly flags the first edit as "unsaved" rather than
// pinning a blank draft as if it were already committed.
const _origRehydrate = rehydrateDraft
function rehydrateDraftAndMark(ctx: RehydrateContext): void {
  _origRehydrate(ctx)
  const hasCommitted = Boolean(
    ctx.placement?.last_options
    && typeof ctx.placement.last_options === 'object',
  )
  if (hasCommitted) markCommitted()
}

// ---- Public composable ----
export function useBitmapDraft() {
  return {
    bitmap: _bitmap,
    curves: _curves,
    typo: _typo,
    mono: _mono,
    multicolor: _multicolor,
    monoPenSlot: _monoPenSlot,
    monoMasterStyleId: _monoMasterStyleId,
    multicolorMasterStyleId: _multicolorMasterStyleId,
    paletteFollowsPens: _paletteFollowsPens,
    committed: _committed,
    isDirty: _isDirty,
    printMode: _printMode,
    expectedLayerCount: _expectedLayerCount,
    segmentationTouched: _segmentationTouched,
    setPrintMode,
    setMasterStyle,
    setMulticolorMasterStyle,
    setMonoInkColor,
    setMonoAdvancedMode,
    getMonoStyleKnobs,
    setMonoKnob,
    setMonoBandOverride,
    resetMonoStyleKnobs,
    getMulticolorStyleKnobs,
    setMulticolorKnob,
    resetMulticolorStyleKnobs,
    interpolatedBandOptions,
    markSegmentationTouched,
    rehydrateDraft: rehydrateDraftAndMark,
    applyPresetOptions,
    buildSegmentationOptions,
    buildAlgorithmOptions,
    buildBitmapOptions,
    buildTypographyOptions,
    markCommitted,
  }
}
