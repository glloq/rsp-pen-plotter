// Unified registry for everything the editor calls a "style" or
// "algorithm". Three previously-separate sources are merged here so the
// UI has a single source of truth and the consolidated picker/galleries
// don't have to query multiple modules.
//
//   - ALGORITHMS:   per-algorithm option schemas (defaults + knob types)
//                   — backend renderers in
//                   ``backend/pen_plotter/converters/algorithms/*.py``.
//   - PRINT_STYLES: named bundles that the operator picks in one click.
//                   Two scopes:
//                     * scope='master' → owns segmentation method,
//                       default algorithm, AND a per-band recipe used
//                       after upload to override each produced layer.
//                     * scope='layer'  → algorithm + options preset for
//                       a single layer/pass. No segmentation responsibility.

// =====================================================================
// Algorithms (was algorithmSchemas.ts)
// =====================================================================

export type AlgorithmId =
  | 'direct'
  | 'halftone'
  | 'stippling'
  | 'crosshatch'
  | 'contours'
  | 'edges'
  | 'centerline'
  | 'spiral'
  | 'scanlines'
  | 'tsp'
  // Algorithms shipped on the backend but historically not surfaced in
  // the registry — exposing them unlocks new layer-level presets and
  // the colour-master recipes below.
  | 'flowfield'
  | 'hilbert'
  | 'gosper'
  | 'eulerian_hatch'
  | 'concentric_offset'
  | 'tsp_opt'
  | 'voronoi_stipple'
  | 'squiggle'

export interface AlgoOption {
  key: string
  // i18n label key, e.g. ``convert.cellSize``. Consumers run this
  // through ``t()`` themselves so the schema stays framework-agnostic.
  label: string
  type: 'number' | 'boolean'
  min?: number
  max?: number
  step?: number
}

export interface AlgorithmSpec {
  id: AlgorithmId
  defaults: Record<string, unknown>
  schema: AlgoOption[]
}

export const ALGORITHMS: Record<AlgorithmId, AlgorithmSpec> = {
  direct: { id: 'direct', defaults: {}, schema: [] },
  halftone: {
    id: 'halftone',
    defaults: { cell_size_px: 6 },
    schema: [
      { key: 'cell_size_px', label: 'convert.cellSize', type: 'number', min: 1, max: 64, step: 1 },
    ],
  },
  stippling: {
    id: 'stippling',
    defaults: { density: 0.02, dot_radius_px: 0.6, seed: 0 },
    schema: [
      {
        key: 'density',
        label: 'convert.density',
        type: 'number',
        min: 0.001,
        max: 0.5,
        step: 0.001,
      },
      {
        key: 'dot_radius_px',
        label: 'convert.dotRadius',
        type: 'number',
        min: 0.1,
        max: 5,
        step: 0.1,
      },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  crosshatch: {
    id: 'crosshatch',
    defaults: { angle_deg: 45, spacing_px: 4, crossed: false },
    schema: [
      { key: 'angle_deg', label: 'convert.angleDeg', type: 'number', min: 0, max: 180, step: 1 },
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'crossed', label: 'convert.crossed', type: 'boolean' },
    ],
  },
  contours: {
    id: 'contours',
    defaults: { spacing_px: 4, max_rings: 20 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'max_rings', label: 'convert.maxRings', type: 'number', min: 1, max: 100, step: 1 },
    ],
  },
  edges: {
    id: 'edges',
    defaults: { stroke_width: 0.8 },
    schema: [
      {
        key: 'stroke_width',
        label: 'convert.strokeWidthPx',
        type: 'number',
        min: 0.1,
        max: 5,
        step: 0.1,
      },
    ],
  },
  centerline: {
    id: 'centerline',
    defaults: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
    schema: [
      {
        key: 'stroke_width',
        label: 'convert.strokeWidthPx',
        type: 'number',
        min: 0.1,
        max: 5,
        step: 0.1,
      },
      { key: 'smooth', label: 'convert.smooth', type: 'boolean' },
      {
        key: 'min_branch_px',
        label: 'convert.minBranch',
        type: 'number',
        min: 0,
        max: 50,
        step: 1,
      },
    ],
  },
  spiral: {
    id: 'spiral',
    defaults: { spacing_px: 4, samples_per_turn: 64 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      {
        key: 'samples_per_turn',
        label: 'convert.samplesPerTurn',
        type: 'number',
        min: 16,
        max: 256,
        step: 1,
      },
    ],
  },
  scanlines: {
    id: 'scanlines',
    defaults: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'wave_amp_px', label: 'convert.waveAmp', type: 'number', min: 0, max: 20, step: 0.5 },
      {
        key: 'wave_period_px',
        label: 'convert.wavePeriod',
        type: 'number',
        min: 2,
        max: 50,
        step: 0.5,
      },
    ],
  },
  tsp: {
    id: 'tsp',
    defaults: { density: 0.02, seed: 0 },
    schema: [
      {
        key: 'density',
        label: 'convert.density',
        type: 'number',
        min: 0.001,
        max: 0.5,
        step: 0.001,
      },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  flowfield: {
    id: 'flowfield',
    defaults: {
      seed_spacing_px: 6,
      step_px: 0.8,
      max_steps: 800,
      bidirectional: true,
      noise_scale: 32,
      seed: 0,
    },
    schema: [
      {
        key: 'seed_spacing_px',
        label: 'convert.spacing',
        type: 'number',
        min: 2,
        max: 30,
        step: 0.5,
      },
      { key: 'step_px', label: 'convert.stepPx', type: 'number', min: 0.2, max: 3, step: 0.1 },
      { key: 'max_steps', label: 'convert.maxSteps', type: 'number', min: 50, max: 4000, step: 50 },
      { key: 'bidirectional', label: 'convert.bidirectional', type: 'boolean' },
      {
        key: 'noise_scale',
        label: 'convert.noiseScale',
        type: 'number',
        min: 4,
        max: 128,
        step: 1,
      },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  hilbert: {
    id: 'hilbert',
    defaults: { spacing_px: 4, min_run_px: 3 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'min_run_px', label: 'convert.minRunPx', type: 'number', min: 1, max: 20, step: 1 },
    ],
  },
  gosper: {
    id: 'gosper',
    defaults: { order: 4, spacing_px: 4, rotation_deg: 0 },
    schema: [
      { key: 'order', label: 'convert.gosperOrder', type: 'number', min: 1, max: 6, step: 1 },
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'rotation_deg', label: 'convert.angleDeg', type: 'number', min: 0, max: 360, step: 5 },
    ],
  },
  eulerian_hatch: {
    id: 'eulerian_hatch',
    defaults: { spacing_px: 4, angle_deg: 45, crossed: false },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'angle_deg', label: 'convert.angleDeg', type: 'number', min: 0, max: 180, step: 1 },
      { key: 'crossed', label: 'convert.crossed', type: 'boolean' },
    ],
  },
  concentric_offset: {
    id: 'concentric_offset',
    defaults: { spacing_px: 3, max_rings: 50, bridge: true },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'max_rings', label: 'convert.maxRings', type: 'number', min: 1, max: 200, step: 1 },
      { key: 'bridge', label: 'convert.bridge', type: 'boolean' },
    ],
  },
  tsp_opt: {
    id: 'tsp_opt',
    defaults: { density: 0.02, max_points: 4000, time_budget_s: 1.5, seed: 0, poisson_disk: true },
    schema: [
      {
        key: 'density',
        label: 'convert.density',
        type: 'number',
        min: 0.001,
        max: 0.5,
        step: 0.001,
      },
      {
        key: 'max_points',
        label: 'convert.maxPoints',
        type: 'number',
        min: 100,
        max: 20000,
        step: 100,
      },
      {
        key: 'time_budget_s',
        label: 'convert.timeBudgetS',
        type: 'number',
        min: 0.1,
        max: 10,
        step: 0.1,
      },
      { key: 'poisson_disk', label: 'convert.poissonDisk', type: 'boolean' },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  voronoi_stipple: {
    id: 'voronoi_stipple',
    defaults: { density: 0.02, dot_radius_px: 0.6, iterations: 6, seed: 0 },
    schema: [
      {
        key: 'density',
        label: 'convert.density',
        type: 'number',
        min: 0.001,
        max: 0.5,
        step: 0.001,
      },
      {
        key: 'dot_radius_px',
        label: 'convert.dotRadius',
        type: 'number',
        min: 0.1,
        max: 5,
        step: 0.1,
      },
      { key: 'iterations', label: 'convert.iterations', type: 'number', min: 0, max: 30, step: 1 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  squiggle: {
    id: 'squiggle',
    defaults: { spacing_px: 4, amp_px: 1.4, period_px: 8, jitter: 0.4, seed: 0 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'amp_px', label: 'convert.waveAmp', type: 'number', min: 0.1, max: 8, step: 0.1 },
      { key: 'period_px', label: 'convert.wavePeriod', type: 'number', min: 2, max: 40, step: 0.5 },
      { key: 'jitter', label: 'convert.jitter', type: 'number', min: 0, max: 1, step: 0.05 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
}

export function getAlgorithm(id: string | null | undefined): AlgorithmSpec | null {
  if (!id) return null
  return (ALGORITHMS as Record<string, AlgorithmSpec>)[id] ?? null
}

export function defaultsFor(id: string): Record<string, unknown> {
  return { ...(getAlgorithm(id)?.defaults ?? {}) }
}

// =====================================================================
// Styles — master (segmentation + per-band recipe) and layer (per-layer
// algorithm preset)
// =====================================================================

export type StyleScope = 'master' | 'layer'
export type PrintStyleKind = 'image' | 'schematic' | 'text'
export type SegmentationMethod = 'kmeans' | 'luminance_bands' | 'thresholds' | 'fixed_palette'
// Master styles split by print mode: ``monochrome`` styles drive the
// mono master pipeline (luminance_bands / thresholds + bandRecipe).
// ``multicolor`` styles drive the multicolour pipeline (kmeans /
// fixed_palette + colorRecipe). Layer styles are mode-agnostic.
export type PrintStyleMode = 'monochrome' | 'multicolor'

// What an applied recipe sends per band/layer. Mirrors the
// ``algorithm`` + ``algorithm_options`` pair the backend's /rerender
// endpoint expects.
export interface BandRecipe {
  algorithm: AlgorithmId
  algorithm_options: Record<string, unknown>
}

// Segmentation block carried by master styles. Drives what
// SourceSection ships at upload time. Layer styles have no segmentation
// responsibility.
export interface StyleSegmentation {
  method: SegmentationMethod
  default_num_bands?: number // luminance_bands
  default_threshold?: number // thresholds (single split → binary)
  default_num_colors?: number // kmeans
  drop_background: boolean
  background_luminance: number
  // When true, the UI exposes a bands slider for this style (mainly
  // shaded modes). Binary modes hide it.
  knob_bands: boolean
  // Preferred segmentation canvas size (``max_dimension_px``) when this
  // style is applied. Line-art / outline / centerline styles set a high
  // value here: at the global 800 px default, fine strokes blur together
  // and the outline trace collapses detail. Omitted → the operator's
  // current detail tier is left untouched.
  default_max_dimension_px?: number
}

export interface PrintStyle {
  id: string
  labelKey: string
  descriptionKey?: string
  applicableTo: PrintStyleKind[]
  scope: StyleScope

  // Master-style print mode. ``undefined`` means the style works in
  // both modes (legacy contract — only mono masters existed pre-merge,
  // so omitted = monochrome). Layer styles ignore this field.
  mode?: PrintStyleMode

  // Master styles segment the bitmap themselves; layer styles inherit
  // the colors tab's segmentation untouched.
  segmentation?: StyleSegmentation

  // Default algorithm + options used when the style is applied. For
  // master styles this is what /upload renders with before per-band
  // overrides; for layer styles this is what /rerender installs.
  defaultAlgorithm: AlgorithmId
  defaultAlgorithmOptions: Record<string, unknown>

  // Optional per-band override applied after /upload finishes. Only
  // master shaded modes set this (Pencil, Halftone shaded, Stippling
  // photo, Engraving, Contours-topo). Binary master modes and layer
  // styles leave it undefined.
  bandRecipe?: (bandIndex: number, totalBands: number) => BandRecipe | null

  // Per-colour-cluster recipe for multicolour master styles. ``colorIndex``
  // is the cluster's position in the layer order (darkest first, mirroring
  // ``bandRecipe``); ``totalColors`` is the cluster count; ``hex`` is the
  // cluster's RGB centroid (so recipes that tune by hue — CMYK halftone
  // angles, e.g. — can branch on it). Returns null to fall back to the
  // style's default algorithm + options for that cluster.
  colorRecipe?: (colorIndex: number, totalColors: number, hex: string) => BandRecipe | null
}

// Helper: linear interpolation across band index for spacing / density
// recipes. ``i`` 0..total-1, returns ``from`` at i=0 and ``to`` at
// i=total-1 (or ``from`` if total<=1). Exported so ``useBitmapDraft``
// can reuse it when synthesising per-band recipes from operator-tuned
// ranges.
export function lerp(i: number, total: number, from: number, to: number): number {
  if (total <= 1) return from
  return from + (to - from) * (i / (total - 1))
}

// Default min/max ranges + angle lists for the monochrome master
// styles. These mirror the constants that used to live inline in each
// ``bandRecipe`` below; hoisting them lets ``useBitmapDraft.defaultMono()``
// pre-populate the operator-facing knobs from the same source of truth
// the fallback ``bandRecipe`` still uses.
export const MONO_STYLE_DEFAULTS: Record<string, Record<string, unknown>> = {
  pencil: {
    spacing_min: 2.5,
    spacing_max: 6.5,
    // Limited to the four angles the chip picker exposes (0/45/90/135)
    // so the active state of each chip on first paint matches the
    // operator's intuition. The 30°/150° pair that lived here pre-
    // refactor wasn't selectable from the UI, only visible after a
    // /preview round-trip — confusing.
    angles: [45, 135, 0, 90],
    crossed_on_darkest: true,
  },
  'halftone-shade': {
    cell_min: 3,
    cell_max: 9,
  },
  'stippling-shade': {
    density_min: 0.012,
    // Darkest band: ~15% of region pixels become dots. The old 0.06
    // (6%) read too faint to register as a dark tone; the slider now
    // reaches 0.5 so very dense stippling is reachable for true blacks.
    density_max: 0.15,
    dot_radius: 0.5,
  },
  engraving: {
    spacing_min: 1.8,
    spacing_max: 5,
    wave_min: 0.6,
    wave_max: 1.6,
    wave_period: 14,
  },
  'contours-topo': {
    spacing_min: 2.5,
    spacing_max: 6,
    rings_min: 10,
    rings_max: 30,
  },
  outline: {
    stroke_width: 0.8,
  },
  tsp: {
    density: 0.04,
  },
  'spiral-master': {
    spacing_px: 4,
    // Radial wobble amplitude lerped dark→light across the bands.
    wave_amp_min: 0.2,
    wave_amp_max: 6,
    waves_per_turn: 12,
  },
  'centerline-trace': {
    stroke_width: 0.8,
  },
}

// Defaults for the multicolour master family. Mirrors MONO_STYLE_DEFAULTS:
// each entry is the operator-tunable knob set for one style, hoisted so
// ``useBitmapDraft.defaultMulticolor()`` can pre-populate the params
// card and the registry's ``colorRecipe`` can read the same values.
// Ranges that lerp across clusters use ``_min`` (applied to the darkest
// cluster) / ``_max`` (lightest cluster) pairs — same convention as
// the mono recipes so the DualRangeSlider component is reusable.
export const MULTICOLOR_STYLE_DEFAULTS: Record<string, Record<string, unknown>> = {
  'color-flat': {
    // Aplats sans paramètres modulables ; gardé vide pour que la carte
    // params affiche un placeholder explicite plutôt qu'un slider
    // factice.
  },
  'color-crosshatch': {
    spacing_min: 2.5,
    spacing_max: 6,
    angle_step: 45,
    crossed: false,
  },
  'color-stipple': {
    density_min: 0.012,
    density_max: 0.05,
    dot_radius: 0.5,
    iterations: 4,
  },
  'color-halftone-cmyk': {
    cell_size: 5,
  },
  'color-contours-topo': {
    spacing_min: 2.5,
    spacing_max: 6,
    rings_min: 10,
    rings_max: 30,
  },
  'color-flowfield': {
    seed_spacing_min: 6,
    seed_spacing_max: 12,
    step_px: 0.8,
    max_steps: 600,
    noise_scale: 48,
    bidirectional: true,
  },
  'color-sketch': {
    spacing_min: 3,
    spacing_max: 6,
    amp_min: 0.6,
    amp_max: 1.8,
    period_px: 8,
    jitter: 0.45,
  },
  'color-spiral': {
    spacing_min: 2,
    spacing_max: 5,
    max_rings: 40,
  },
  'color-stippling-classic': {
    density_min: 0.012,
    density_max: 0.05,
    dot_radius: 0.5,
  },
  'color-edges': {
    stroke_width: 0.8,
  },
  'color-centerline': {
    stroke_width: 0.8,
    min_branch_px: 3,
  },
  'color-spiral-classic': {
    spacing_min: 2,
    spacing_max: 5,
    samples_per_turn: 64,
  },
  'color-scanlines': {
    spacing_min: 2.5,
    spacing_max: 6,
    wave_amp_px: 0,
    wave_period_px: 12,
  },
  'color-tsp': {
    density_min: 0.012,
    density_max: 0.05,
  },
  'color-hilbert': {
    spacing_min: 2.5,
    spacing_max: 6,
    min_run_px: 3,
  },
  'color-gosper': {
    order: 4,
    spacing_min: 3,
    spacing_max: 5,
  },
  'color-eulerian': {
    spacing_min: 2.5,
    spacing_max: 6,
    angle_step: 45,
    crossed: false,
  },
  'color-tsp-opt': {
    density_min: 0.012,
    density_max: 0.05,
    max_points: 4000,
    time_budget_s: 1.5,
  },
}

// Naming convention to resolve old collisions between mono modes and
// per-layer presets:
//   - master shaded photo modes keep simple ids: pencil, halftone-shade,
//     stippling-shade, engraving, contours-topo, spiral-master (tonal
//     amplitude-modulated spiral)
//   - master binary modes: outline, tsp
//   - layer presets keep their original ids (direct, halftone-fine,
//     halftone-coarse, stippling-portrait, crosshatch-tech, contours,
//     edges, spiral, scanlines)
// Ids that previously clashed (``contours`` was both a mono mode and a
// layer preset, ``spiral`` likewise) now have distinct ids; placement
// rehydration maps the old ids to the new ones in ``useBitmapDraft``.

export const PRINT_STYLES: PrintStyle[] = [
  // ============== MASTER STYLES — shaded (luminance bands) ==============
  {
    id: 'pencil',
    labelKey: 'mono.modes.pencil',
    descriptionKey: 'mono.modes.pencilDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'luminance_bands',
      // Default to a single luminance band → one layer, one pen. The
      // shading slider (knob_bands) lets the operator add bands when they
      // want tonal shading; each extra band is an extra layer they opt
      // into explicitly.
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'crosshatch',
    defaultAlgorithmOptions: { angle_deg: 45, spacing_px: 4, crossed: false },
    bandRecipe(i, total) {
      const angles = [45, 135, 0, 90, 30, 150]
      const angle = angles[i % angles.length] ?? 45
      const spacing = lerp(i, total, 2.5, 6.5)
      const crossed = i === 0 && total > 1
      return {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: angle, spacing_px: spacing, crossed },
      }
    },
  },
  {
    id: 'halftone-shade',
    labelKey: 'mono.modes.halftone',
    descriptionKey: 'mono.modes.halftoneDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'luminance_bands',
      // Default to a single luminance band → one layer, one pen. The
      // shading slider (knob_bands) lets the operator add bands when they
      // want tonal shading; each extra band is an extra layer they opt
      // into explicitly.
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'halftone',
    defaultAlgorithmOptions: { cell_size_px: 5 },
    bandRecipe(i, total) {
      const cell = lerp(i, total, 3, 9)
      return { algorithm: 'halftone', algorithm_options: { cell_size_px: cell } }
    },
  },
  {
    id: 'stippling-shade',
    labelKey: 'mono.modes.stippling',
    descriptionKey: 'mono.modes.stipplingDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'luminance_bands',
      // Default to a single luminance band → one layer, one pen. The
      // shading slider (knob_bands) lets the operator add bands when they
      // want tonal shading; each extra band is an extra layer they opt
      // into explicitly.
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'stippling',
    defaultAlgorithmOptions: { density: 0.08, dot_radius_px: 0.5, seed: 0 },
    bandRecipe(i, total) {
      const density = lerp(i, total, 0.15, 0.012)
      return {
        algorithm: 'stippling',
        algorithm_options: { density, dot_radius_px: 0.5, seed: i * 7 + 13 },
      }
    },
  },
  {
    id: 'engraving',
    labelKey: 'mono.modes.engraving',
    descriptionKey: 'mono.modes.engravingDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'luminance_bands',
      // Single band by default (one layer, one pen); shading slider adds
      // bands when the operator wants tonal depth.
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'scanlines',
    defaultAlgorithmOptions: { spacing_px: 3, wave_amp_px: 0, wave_period_px: 12 },
    bandRecipe(i, total) {
      const spacing = lerp(i, total, 1.8, 5)
      const wave = lerp(i, total, 0.6, 1.6)
      return {
        algorithm: 'scanlines',
        algorithm_options: { spacing_px: spacing, wave_amp_px: wave, wave_period_px: 14 },
      }
    },
  },
  {
    id: 'contours-topo',
    labelKey: 'mono.modes.contours',
    descriptionKey: 'mono.modes.contoursDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'luminance_bands',
      // Default to a single luminance band → one layer, one pen. The
      // shading slider (knob_bands) lets the operator add bands when they
      // want tonal shading; each extra band is an extra layer they opt
      // into explicitly.
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'contours',
    defaultAlgorithmOptions: { spacing_px: 4, max_rings: 20 },
    bandRecipe(i, total) {
      const spacing = lerp(i, total, 2.5, 6)
      const rings = Math.round(lerp(i, total, 30, 10))
      return {
        algorithm: 'contours',
        algorithm_options: { spacing_px: spacing, max_rings: rings },
      }
    },
  },
  // ============== MASTER STYLES — binary (thresholds) ==============
  {
    id: 'outline',
    labelKey: 'mono.modes.outline',
    descriptionKey: 'mono.modes.outlineDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
      // Line art needs detail: at 800 px the outline trace merges thin
      // strokes and drops fine features. High tier keeps them.
      default_max_dimension_px: 2400,
    },
    defaultAlgorithm: 'edges',
    defaultAlgorithmOptions: { stroke_width: 0.8 },
    bandRecipe() {
      return { algorithm: 'edges', algorithm_options: { stroke_width: 0.8 } }
    },
  },
  {
    id: 'tsp',
    labelKey: 'mono.modes.tsp',
    descriptionKey: 'mono.modes.tspDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
    },
    defaultAlgorithm: 'tsp',
    defaultAlgorithmOptions: { density: 0.04, seed: 0 },
    bandRecipe() {
      return { algorithm: 'tsp', algorithm_options: { density: 0.04, seed: 0 } }
    },
  },
  {
    id: 'spiral-master',
    labelKey: 'mono.modes.spiral',
    descriptionKey: 'mono.modes.spiralDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'monochrome',
    // Tonal spiral: one Archimedean spiral over the whole image, its
    // radial wobble amplitude lerped across luminance bands (dark = big
    // wobble, light = nearly straight). drop_background stays OFF so the
    // spiral is continuous edge-to-edge — the iconic "spiral portrait"
    // look — instead of leaving holes in the highlights.
    segmentation: {
      method: 'luminance_bands',
      default_num_bands: 6,
      drop_background: false,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'spiral',
    defaultAlgorithmOptions: {
      spacing_px: 4,
      samples_per_turn: 64,
      wave_amp_px: 2,
      waves_per_turn: 12,
    },
    bandRecipe(i, total) {
      // Darkest band (i=0) → max amplitude, lightest → a thin wobble.
      const amp = lerp(i, total, 6, 0.2)
      return {
        algorithm: 'spiral',
        algorithm_options: {
          spacing_px: 4,
          samples_per_turn: 64,
          wave_amp_px: amp,
          waves_per_turn: 12,
        },
      }
    },
  },
  {
    id: 'centerline-trace',
    labelKey: 'mono.modes.centerline',
    descriptionKey: 'mono.modes.centerlineDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'master',
    mode: 'monochrome',
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
      // Skeleton tracing on a downscaled canvas fuses nearby strokes
      // into one centreline; keep the source large so each stroke stays
      // separable.
      default_max_dimension_px: 2400,
    },
    defaultAlgorithm: 'centerline',
    defaultAlgorithmOptions: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
    bandRecipe() {
      return {
        algorithm: 'centerline',
        algorithm_options: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
      }
    },
  },
  // ============== MASTER STYLES — multicolor ==============
  // Mirror of the mono master family for multicolour mode: each style
  // owns its segmentation (kmeans by default) and a ``colorRecipe`` the
  // composable expands into ``band_recipes`` per detected colour cluster.
  // The backend's existing band_recipes machinery serves both modes —
  // recipes are matched by cluster order (darkest first) regardless of
  // whether segmentation is luminance bands or kmeans clusters.
  {
    id: 'color-flat',
    labelKey: 'colorStyles.flat',
    descriptionKey: 'colorStyles.flatDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'direct',
    defaultAlgorithmOptions: {},
    colorRecipe() {
      return { algorithm: 'direct', algorithm_options: {} }
    },
  },
  {
    id: 'color-crosshatch',
    labelKey: 'colorStyles.crosshatch',
    descriptionKey: 'colorStyles.crosshatchDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 5,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'crosshatch',
    defaultAlgorithmOptions: { angle_deg: 45, spacing_px: 4, crossed: false },
    colorRecipe(i, total) {
      // Rotate the hatch angle per cluster so overlapping inks read as
      // distinct strokes. Darkest cluster gets the densest spacing so the
      // visual weight tracks the source-image luminance.
      const angles = [0, 45, 90, 135, 30, 75, 120, 165]
      const angle = angles[i % angles.length] ?? 45
      const spacing = lerp(i, total, 2.5, 6)
      return {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: angle, spacing_px: spacing, crossed: false },
      }
    },
  },
  {
    id: 'color-stipple',
    labelKey: 'colorStyles.stipple',
    descriptionKey: 'colorStyles.stippleDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 5,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'voronoi_stipple',
    defaultAlgorithmOptions: { density: 0.03, dot_radius_px: 0.5, iterations: 4, seed: 0 },
    colorRecipe(i, total) {
      // Darker clusters get denser dot fields. Voronoi relaxation keeps
      // spacing even within each cluster so overlapping inks don't clump.
      const density = lerp(i, total, 0.05, 0.012)
      return {
        algorithm: 'voronoi_stipple',
        algorithm_options: {
          density,
          dot_radius_px: 0.5,
          iterations: 4,
          seed: i * 13 + 7,
        },
      }
    },
  },
  {
    id: 'color-halftone-cmyk',
    labelKey: 'colorStyles.halftoneCmyk',
    descriptionKey: 'colorStyles.halftoneCmykDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'halftone',
    defaultAlgorithmOptions: { cell_size_px: 5 },
    colorRecipe(_i, _total, hex) {
      // CMYK printing convention: assign canonical screen angles by the
      // cluster's dominant primary. Falls back to 45° (the black plate
      // angle) when no single channel dominates. Cell size stays uniform
      // so the trade-off is colour overlay vs moiré — the classic look.
      const r = parseInt(hex.slice(1, 3), 16) / 255
      const g = parseInt(hex.slice(3, 5), 16) / 255
      const b = parseInt(hex.slice(5, 7), 16) / 255
      const c = 1 - r,
        m = 1 - g,
        y = 1 - b
      let angle = 45
      const max = Math.max(c, m, y)
      if (max > 0.15) {
        if (max === c) angle = 15
        else if (max === m) angle = 75
        else angle = 0 // yellow
      }
      return {
        algorithm: 'halftone',
        algorithm_options: { cell_size_px: 5, angle_deg: angle },
      }
    },
  },
  {
    id: 'color-contours-topo',
    labelKey: 'colorStyles.contoursTopo',
    descriptionKey: 'colorStyles.contoursTopoDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 5,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'contours',
    defaultAlgorithmOptions: { spacing_px: 4, max_rings: 20 },
    colorRecipe(i, total) {
      const spacing = lerp(i, total, 2.5, 6)
      const rings = Math.round(lerp(i, total, 30, 10))
      return {
        algorithm: 'contours',
        algorithm_options: { spacing_px: spacing, max_rings: rings },
      }
    },
  },
  {
    id: 'color-flowfield',
    labelKey: 'colorStyles.flowfield',
    descriptionKey: 'colorStyles.flowfieldDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'flowfield',
    defaultAlgorithmOptions: {
      seed_spacing_px: 8,
      step_px: 0.8,
      max_steps: 600,
      bidirectional: true,
      noise_scale: 48,
      mode: 'gradient',
      seed: 0,
    },
    colorRecipe(i, _total) {
      // Stagger the streamline density per cluster: lighter clusters
      // get sparser seeds so the overlapping inks don't muddy the
      // image. Each cluster also gets its own RNG seed so the
      // streamlines don't trace identical paths just shifted in colour.
      return {
        algorithm: 'flowfield',
        algorithm_options: {
          seed_spacing_px: 6 + i * 2,
          step_px: 0.8,
          max_steps: 600,
          bidirectional: true,
          noise_scale: 48,
          mode: 'gradient',
          seed: i * 31 + 11,
        },
      }
    },
  },
  {
    id: 'color-sketch',
    labelKey: 'colorStyles.sketch',
    descriptionKey: 'colorStyles.sketchDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.9,
      knob_bands: false,
    },
    defaultAlgorithm: 'squiggle',
    defaultAlgorithmOptions: {
      spacing_px: 4,
      amp_px: 1.4,
      period_px: 8,
      jitter: 0.45,
      mode: 'modulated',
      seed: 0,
    },
    colorRecipe(i, total) {
      // Loose, hand-drawn feel: amplitude shrinks for lighter clusters
      // so the wiggle reads as shading instead of dominant texture.
      const amp = lerp(i, total, 1.8, 0.6)
      const spacing = lerp(i, total, 3, 6)
      return {
        algorithm: 'squiggle',
        algorithm_options: {
          spacing_px: spacing,
          amp_px: amp,
          period_px: 8,
          jitter: 0.45,
          mode: 'modulated',
          seed: i * 17 + 23,
        },
      }
    },
  },
  {
    id: 'color-spiral',
    labelKey: 'colorStyles.spiral',
    descriptionKey: 'colorStyles.spiralDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'concentric_offset',
    defaultAlgorithmOptions: { spacing_px: 3, max_rings: 40, bridge: true },
    colorRecipe(i, total) {
      // Tighter rings on the darker cluster, looser on the light side.
      const spacing = lerp(i, total, 2, 5)
      return {
        algorithm: 'concentric_offset',
        algorithm_options: { spacing_px: spacing, max_rings: 40, bridge: true },
      }
    },
  },
  // ---- Additional colour masters to cover every backend algorithm ----
  // The layer picker exposes 18 algorithms; the colour master family
  // mirrors them one-for-one so the operator can pick a multi-colour
  // preset based on any technique, not just the eight we shipped first.
  {
    id: 'color-stippling-classic',
    labelKey: 'colorStyles.stipplingClassic',
    descriptionKey: 'colorStyles.stipplingClassicDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 5,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'stippling',
    defaultAlgorithmOptions: { density: 0.03, dot_radius_px: 0.5, seed: 0 },
    colorRecipe(i, total) {
      const density = lerp(i, total, 0.05, 0.012)
      return {
        algorithm: 'stippling',
        algorithm_options: { density, dot_radius_px: 0.5, seed: i * 7 + 13 },
      }
    },
  },
  {
    id: 'color-edges',
    labelKey: 'colorStyles.edges',
    descriptionKey: 'colorStyles.edgesDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 5,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
      default_max_dimension_px: 2400,
    },
    defaultAlgorithm: 'edges',
    defaultAlgorithmOptions: { stroke_width: 0.8 },
    colorRecipe() {
      return { algorithm: 'edges', algorithm_options: { stroke_width: 0.8 } }
    },
  },
  {
    id: 'color-centerline',
    labelKey: 'colorStyles.centerline',
    descriptionKey: 'colorStyles.centerlineDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
      default_max_dimension_px: 2400,
    },
    defaultAlgorithm: 'centerline',
    defaultAlgorithmOptions: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
    colorRecipe() {
      return {
        algorithm: 'centerline',
        algorithm_options: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
      }
    },
  },
  {
    id: 'color-spiral-classic',
    labelKey: 'colorStyles.spiralClassic',
    descriptionKey: 'colorStyles.spiralClassicDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'spiral',
    defaultAlgorithmOptions: { spacing_px: 3, samples_per_turn: 64 },
    colorRecipe(i, total) {
      const spacing = lerp(i, total, 2, 5)
      return {
        algorithm: 'spiral',
        algorithm_options: { spacing_px: spacing, samples_per_turn: 64 },
      }
    },
  },
  {
    id: 'color-scanlines',
    labelKey: 'colorStyles.scanlines',
    descriptionKey: 'colorStyles.scanlinesDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'scanlines',
    defaultAlgorithmOptions: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
    colorRecipe(i, total) {
      const spacing = lerp(i, total, 2.5, 6)
      return {
        algorithm: 'scanlines',
        algorithm_options: { spacing_px: spacing, wave_amp_px: 0, wave_period_px: 12 },
      }
    },
  },
  {
    id: 'color-tsp',
    labelKey: 'colorStyles.tsp',
    descriptionKey: 'colorStyles.tspDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'tsp',
    defaultAlgorithmOptions: { density: 0.03, seed: 0 },
    colorRecipe(i, total) {
      const density = lerp(i, total, 0.05, 0.012)
      return {
        algorithm: 'tsp',
        algorithm_options: { density, seed: i * 11 + 5 },
      }
    },
  },
  {
    id: 'color-hilbert',
    labelKey: 'colorStyles.hilbert',
    descriptionKey: 'colorStyles.hilbertDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'hilbert',
    defaultAlgorithmOptions: { spacing_px: 4, min_run_px: 3 },
    colorRecipe(i, total) {
      const spacing = lerp(i, total, 2.5, 6)
      return {
        algorithm: 'hilbert',
        algorithm_options: { spacing_px: spacing, min_run_px: 3 },
      }
    },
  },
  {
    id: 'color-gosper',
    labelKey: 'colorStyles.gosper',
    descriptionKey: 'colorStyles.gosperDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'gosper',
    defaultAlgorithmOptions: { order: 4, spacing_px: 4, rotation_deg: 0 },
    colorRecipe(i, total) {
      const spacing = lerp(i, total, 3, 5)
      // Rotate per cluster to avoid identical curves stacking exactly.
      return {
        algorithm: 'gosper',
        algorithm_options: { order: 4, spacing_px: spacing, rotation_deg: (i * 30) % 360 },
      }
    },
  },
  {
    id: 'color-eulerian',
    labelKey: 'colorStyles.eulerian',
    descriptionKey: 'colorStyles.eulerianDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'eulerian_hatch',
    defaultAlgorithmOptions: { spacing_px: 4, angle_deg: 45, crossed: false },
    colorRecipe(i, total) {
      const angles = [0, 45, 90, 135, 30, 75, 120, 165]
      const angle = angles[i % angles.length] ?? 45
      const spacing = lerp(i, total, 2.5, 6)
      return {
        algorithm: 'eulerian_hatch',
        algorithm_options: { spacing_px: spacing, angle_deg: angle, crossed: false },
      }
    },
  },
  {
    id: 'color-tsp-opt',
    labelKey: 'colorStyles.tspOpt',
    descriptionKey: 'colorStyles.tspOptDesc',
    applicableTo: ['image'],
    scope: 'master',
    mode: 'multicolor',
    segmentation: {
      method: 'kmeans',
      default_num_colors: 4,
      drop_background: true,
      background_luminance: 0.92,
      knob_bands: false,
    },
    defaultAlgorithm: 'tsp_opt',
    defaultAlgorithmOptions: {
      density: 0.03,
      max_points: 4000,
      time_budget_s: 1.5,
      seed: 0,
      poisson_disk: true,
    },
    colorRecipe(i, total) {
      const density = lerp(i, total, 0.05, 0.012)
      return {
        algorithm: 'tsp_opt',
        algorithm_options: {
          density,
          max_points: 4000,
          time_budget_s: 1.5,
          seed: i * 19 + 3,
          poisson_disk: true,
        },
      }
    },
  },

  // ============== LAYER STYLES — per-layer presets ==============
  {
    id: 'direct',
    labelKey: 'printStyles.direct',
    descriptionKey: 'printStyles.directDesc',
    applicableTo: ['image', 'schematic', 'text'],
    scope: 'layer',
    defaultAlgorithm: 'direct',
    defaultAlgorithmOptions: {},
  },
  {
    id: 'halftone-fine',
    labelKey: 'printStyles.halftoneFine',
    descriptionKey: 'printStyles.halftoneFineDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'halftone',
    defaultAlgorithmOptions: { cell_size_px: 4 },
  },
  {
    id: 'halftone-coarse',
    labelKey: 'printStyles.halftoneCoarse',
    descriptionKey: 'printStyles.halftoneCoarseDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'halftone',
    defaultAlgorithmOptions: { cell_size_px: 10 },
  },
  {
    id: 'stippling-portrait',
    labelKey: 'printStyles.stippling',
    descriptionKey: 'printStyles.stipplingDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'stippling',
    defaultAlgorithmOptions: { density: 0.03, dot_radius_px: 0.5, seed: 0 },
  },
  {
    id: 'crosshatch-tech',
    labelKey: 'printStyles.crosshatch',
    descriptionKey: 'printStyles.crosshatchDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'layer',
    defaultAlgorithm: 'crosshatch',
    defaultAlgorithmOptions: { angle_deg: 45, spacing_px: 4, crossed: true },
  },
  {
    id: 'contours',
    labelKey: 'printStyles.contours',
    descriptionKey: 'printStyles.contoursDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'layer',
    defaultAlgorithm: 'contours',
    defaultAlgorithmOptions: { spacing_px: 5, max_rings: 20 },
  },
  {
    id: 'edges',
    labelKey: 'printStyles.edges',
    descriptionKey: 'printStyles.edgesDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'layer',
    defaultAlgorithm: 'edges',
    defaultAlgorithmOptions: { stroke_width: 0.8 },
  },
  {
    id: 'spiral',
    labelKey: 'printStyles.spiral',
    descriptionKey: 'printStyles.spiralDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'spiral',
    defaultAlgorithmOptions: { spacing_px: 4, samples_per_turn: 64 },
  },
  {
    id: 'scanlines',
    labelKey: 'printStyles.scanlines',
    descriptionKey: 'printStyles.scanlinesDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'scanlines',
    defaultAlgorithmOptions: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
  },
  {
    id: 'centerline-stroke',
    labelKey: 'printStyles.centerline',
    descriptionKey: 'printStyles.centerlineDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'layer',
    defaultAlgorithm: 'centerline',
    defaultAlgorithmOptions: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
  },
  {
    id: 'voronoi-stipple',
    labelKey: 'printStyles.voronoiStipple',
    descriptionKey: 'printStyles.voronoiStippleDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'voronoi_stipple',
    defaultAlgorithmOptions: { density: 0.03, dot_radius_px: 0.5, iterations: 6, seed: 0 },
  },
  {
    id: 'squiggle',
    labelKey: 'printStyles.squiggle',
    descriptionKey: 'printStyles.squiggleDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'squiggle',
    defaultAlgorithmOptions: { spacing_px: 4, amp_px: 1.4, period_px: 8, jitter: 0.4, seed: 0 },
  },
  {
    id: 'flowfield',
    labelKey: 'printStyles.flowfield',
    descriptionKey: 'printStyles.flowfieldDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'flowfield',
    defaultAlgorithmOptions: {
      seed_spacing_px: 6,
      step_px: 0.8,
      max_steps: 800,
      bidirectional: true,
      noise_scale: 32,
      seed: 0,
    },
  },
  {
    id: 'hilbert',
    labelKey: 'printStyles.hilbert',
    descriptionKey: 'printStyles.hilbertDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'hilbert',
    defaultAlgorithmOptions: { spacing_px: 4, min_run_px: 3 },
  },
  {
    id: 'gosper',
    labelKey: 'printStyles.gosper',
    descriptionKey: 'printStyles.gosperDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'gosper',
    defaultAlgorithmOptions: { order: 4, spacing_px: 4, rotation_deg: 0 },
  },
  {
    id: 'eulerian-hatch',
    labelKey: 'printStyles.eulerianHatch',
    descriptionKey: 'printStyles.eulerianHatchDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'eulerian_hatch',
    defaultAlgorithmOptions: { spacing_px: 4, angle_deg: 45, crossed: false },
  },
  {
    id: 'concentric-offset',
    labelKey: 'printStyles.concentricOffset',
    descriptionKey: 'printStyles.concentricOffsetDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'concentric_offset',
    defaultAlgorithmOptions: { spacing_px: 3, max_rings: 50, bridge: true },
  },
  {
    id: 'tsp-opt',
    labelKey: 'printStyles.tspOpt',
    descriptionKey: 'printStyles.tspOptDesc',
    applicableTo: ['image'],
    scope: 'layer',
    defaultAlgorithm: 'tsp_opt',
    defaultAlgorithmOptions: {
      density: 0.02,
      max_points: 4000,
      time_budget_s: 1.5,
      seed: 0,
      poisson_disk: true,
    },
  },
]

// Default master style applied when the operator first switches to
// monochrome — pencil is the friendliest general-purpose choice for
// photographs.
export const DEFAULT_MASTER_STYLE_ID = 'pencil'

// Default master style applied when the operator switches to
// multicolour. Flat aplats are the most predictable starting point —
// the operator can then promote to crosshatch / stipple / halftone via
// the picker once they see the cluster layout.
export const DEFAULT_MULTICOLOR_STYLE_ID = 'color-flat'

// Legacy master-style ids from before the registry merge. Saved
// placements and variants still carry them; the rehydration path maps
// them to the renamed registry entries so historical state doesn't
// silently break.
export const LEGACY_MASTER_ID_MAP: Record<string, string> = {
  pencil: 'pencil',
  halftone: 'halftone-shade',
  stippling: 'stippling-shade',
  engraving: 'engraving',
  contours: 'contours-topo',
  outline: 'outline',
  tsp: 'tsp',
  spiral: 'spiral-master',
  centerline: 'centerline-trace',
}

// ---- Query helpers ----

export function getStyle(id: string | null | undefined): PrintStyle | undefined {
  if (!id) return undefined
  return PRINT_STYLES.find((s) => s.id === id)
}

export function masterStyles(): PrintStyle[] {
  return PRINT_STYLES.filter((s) => s.scope === 'master')
}

// Filtered master styles by print mode. Styles with an undefined ``mode``
// default to monochrome (historical contract — only mono masters existed
// before the colour-master family landed). Callers pass the active
// ``printMode`` so the picker shows the right gallery.
export function masterStylesByMode(mode: PrintStyleMode): PrintStyle[] {
  return PRINT_STYLES.filter((s) => s.scope === 'master' && (s.mode ?? 'monochrome') === mode)
}

export function layerStyles(kind?: PrintStyleKind): PrintStyle[] {
  const layers = PRINT_STYLES.filter((s) => s.scope === 'layer')
  if (!kind) return layers
  return layers.filter((s) => s.applicableTo.includes(kind))
}

// Resolve a possibly-legacy master style id to a registry entry.
// Returns the default master style if neither the id nor its legacy
// mapping is found, so callers always get something usable.
export function resolveMasterStyle(id: string | null | undefined): PrintStyle {
  if (id) {
    const direct = getStyle(id)
    if (direct && direct.scope === 'master') return direct
    const mapped = LEGACY_MASTER_ID_MAP[id]
    if (mapped) {
      const resolved = getStyle(mapped)
      if (resolved && resolved.scope === 'master') return resolved
    }
  }
  return getStyle(DEFAULT_MASTER_STYLE_ID)!
}

// Sister of ``resolveMasterStyle`` for the multicolour family.
// Falls back to ``DEFAULT_MULTICOLOR_STYLE_ID`` (flat aplats) rather
// than the monochrome default so callers in multicolour mode never end
// up applying a luminance-bands segmentation by accident.
export function resolveMulticolorStyle(id: string | null | undefined): PrintStyle {
  if (id) {
    const direct = getStyle(id)
    if (direct && direct.scope === 'master' && direct.mode === 'multicolor') return direct
  }
  return getStyle(DEFAULT_MULTICOLOR_STYLE_ID)!
}
