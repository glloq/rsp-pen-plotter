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
import { resolveMasterStyle, DEFAULT_MASTER_STYLE_ID } from '../data/printRegistry'

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
  // Mono master styles write their full options dict here directly,
  // bypassing the scattered per-algo fields below. When non-empty it
  // takes precedence in ``buildAlgorithmOptions`` so a master style's
  // recipe survives intact even though the multicolour path still
  // writes to the legacy scattered fields.
  algorithm_options: Record<string, unknown>
  cell_size_px: number
  density: number
  dot_radius_px: number
  seed: number
  crosshatch_angle_deg: number
  crosshatch_spacing_px: number
  crosshatch_crossed: boolean
  contours_spacing_px: number
  contours_max_rings: number
  edges_stroke_width: number
  spiral_spacing_px: number
  spiral_samples_per_turn: number
  scanlines_spacing_px: number
  scanlines_wave_amp_px: number
  scanlines_wave_period_px: number
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
    cell_size_px: 6,
    density: 0.02,
    dot_radius_px: 0.6,
    seed: 0,
    crosshatch_angle_deg: 45,
    crosshatch_spacing_px: 4,
    crosshatch_crossed: false,
    contours_spacing_px: 4,
    contours_max_rings: 20,
    edges_stroke_width: 0.8,
    spiral_spacing_px: 4,
    spiral_samples_per_turn: 64,
    scanlines_spacing_px: 4,
    scanlines_wave_amp_px: 0,
    scanlines_wave_period_px: 12,
  }
}

export function defaultCurves(): CurvesDraft {
  return {
    centerline_mode: false,
    simplify_tolerance_mm: 0.05,
    curve_fit: false,
  }
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
const _paletteFollowsPens = ref<boolean>(true)

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
  const algoOpts = (opts as Record<string, unknown>).algorithm_options as
    | Record<string, unknown>
    | undefined
  if (algoOpts) {
    // Mirror the scattered per-algo fields from the saved
    // algorithm_options dict so re-uploading without changes produces
    // the same SVG. The dict-only migration arrives in Phase 2's UI
    // refactor.
    for (const key of ['cell_size_px', 'density', 'dot_radius_px', 'seed']) {
      if (key in algoOpts) target[key] = algoOpts[key]
    }
  }
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
  const algoOpts = (opts.algorithm_options as Record<string, unknown>) ?? {}
  for (const key of ['cell_size_px', 'density', 'dot_radius_px', 'seed']) {
    if (key in algoOpts) target[key] = algoOpts[key]
  }
}

// Switch between multicolour and monochrome. Rewrites the segmentation
// method, algorithm and post-process knobs to the active master style's
// recipe (mono) or back to a sensible kmeans default (multi). The
// MonochromeCard's mode picker calls this indirectly by mutating the
// draft itself; this helper centralises the "what does mono/multi
// imply for each field?" answer.
export function setPrintMode(mode: 'multicolor' | 'monochrome'): void {
  if (mode === 'monochrome') {
    const style = resolveMasterStyle(_monoMasterStyleId.value)
    const seg = style.segmentation
    if (seg) {
      _bitmap.value.segmentation_method = seg.method
      _bitmap.value.drop_background = seg.drop_background
      _bitmap.value.background_luminance = seg.background_luminance
      _bitmap.value.algorithm = style.defaultAlgorithm
      _bitmap.value.algorithm_options = { ...style.defaultAlgorithmOptions }
      if (seg.method === 'luminance_bands') {
        if (_bitmap.value.num_bands < 2 || _bitmap.value.num_bands > 6) {
          _bitmap.value.num_bands = seg.default_num_bands ?? 4
        }
      } else if (seg.method === 'thresholds') {
        _bitmap.value.thresholds = [seg.default_threshold ?? 0.5]
      }
    }
    // Clear the multicolour palette so a stale ``fixed_palette`` from
    // the previous mode can't keep the preview / upload painting in
    // colour. Without this, switching multi → mono left the operator
    // with N coloured layers because ``buildSegmentationOptions`` would
    // still serve the old palette if anything tipped the
    // segmentation_method back to fixed_palette.
    _bitmap.value.palette = []
    _bitmap.value.num_colors = 1
    _paletteFollowsPens.value = false
  } else {
    _bitmap.value.segmentation_method = 'kmeans'
    _bitmap.value.num_colors = 4
    _bitmap.value.background_luminance = 0.92
    // Clear the master style's options dict so the multicolour path
    // falls back to the per-algo scattered fields and respects any
    // preset applied afterwards.
    _bitmap.value.algorithm_options = {}
    if (
      _bitmap.value.algorithm !== 'direct'
      && _bitmap.value.algorithm !== 'halftone'
      && _bitmap.value.algorithm !== 'stippling'
    ) {
      _bitmap.value.algorithm = 'direct'
    }
    _paletteFollowsPens.value = true
  }
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
  const b = _bitmap.value
  if (Object.keys(b.algorithm_options).length > 0) {
    return { ...b.algorithm_options }
  }
  switch (b.algorithm) {
    case 'halftone':
      return { cell_size_px: b.cell_size_px }
    case 'stippling':
      return { density: b.density, dot_radius_px: b.dot_radius_px, seed: b.seed }
    case 'crosshatch':
      return {
        angle_deg: b.crosshatch_angle_deg,
        spacing_px: b.crosshatch_spacing_px,
        crossed: b.crosshatch_crossed,
      }
    case 'contours':
      return { spacing_px: b.contours_spacing_px, max_rings: b.contours_max_rings }
    case 'edges':
      return { stroke_width: b.edges_stroke_width }
    case 'spiral':
      return { spacing_px: b.spiral_spacing_px, samples_per_turn: b.spiral_samples_per_turn }
    case 'scanlines':
      return {
        spacing_px: b.scanlines_spacing_px,
        wave_amp_px: b.scanlines_wave_amp_px,
        wave_period_px: b.scanlines_wave_period_px,
      }
    case 'tsp':
      return { density: b.density, seed: b.seed }
    default:
      return {}
  }
}

// Build the per-band recipes for the current master style so the
// backend's /preview applies them inline instead of just the uniform
// algorithm. Only emitted in mono shaded mode (where the segmentation
// produces N >= 2 bands and the active style carries a ``bandRecipe``);
// returns ``undefined`` everywhere else so the payload stays minimal.
function buildBandRecipes(): Array<Record<string, unknown>> | undefined {
  if (_printMode.value !== 'monochrome') return undefined
  if (_bitmap.value.segmentation_method !== 'luminance_bands') return undefined
  const style = resolveMasterStyle(_monoMasterStyleId.value)
  if (!style.bandRecipe) return undefined
  const total = _bitmap.value.num_bands
  return Array.from({ length: total }, (_, i) => {
    const recipe = style.bandRecipe!(i, total)
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
  const payload: Record<string, unknown> = {
    algorithm: algo,
    num_colors: b.num_colors,
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
    master_style_id: _monoMasterStyleId.value,
    // Curves tab state — also a backend-unknown extra, read back by
    // ``rehydrateDraft`` so the toggles survive a round-trip.
    curves: { ...c },
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

const _isDirty = computed<boolean>(() => {
  return snap(_bitmap.value) !== _baselineBitmap.value
    || snap(_typo.value) !== _baselineTypo.value
    || snap(_curves.value) !== _baselineCurves.value
})

function markCommitted(): void {
  _baselineBitmap.value = snap(_bitmap.value)
  _baselineTypo.value = snap(_typo.value)
  _baselineCurves.value = snap(_curves.value)
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
    monoPenSlot: _monoPenSlot,
    monoMasterStyleId: _monoMasterStyleId,
    paletteFollowsPens: _paletteFollowsPens,
    committed: _committed,
    isDirty: _isDirty,
    printMode: _printMode,
    expectedLayerCount: _expectedLayerCount,
    setPrintMode,
    rehydrateDraft: rehydrateDraftAndMark,
    applyPresetOptions,
    buildSegmentationOptions,
    buildAlgorithmOptions,
    buildBitmapOptions,
    buildTypographyOptions,
    markCommitted,
  }
}
