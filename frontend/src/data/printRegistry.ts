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
//                       (Replaces ``data/monoModes.ts``.)
//                     * scope='layer'  → algorithm + options preset for
//                       a single layer/pass. No segmentation responsibility.
//                       (Replaces ``data/printStyles.ts``.)
//
// The old modules (``monoModes.ts``, ``printStyles.ts``,
// ``algorithmSchemas.ts``) are kept as @deprecated facades that
// re-export from here so the migration can happen file-by-file without
// breaking imports.

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
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'dot_radius_px', label: 'convert.dotRadius', type: 'number', min: 0.1, max: 5, step: 0.1 },
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
      { key: 'stroke_width', label: 'convert.strokeWidthPx', type: 'number', min: 0.1, max: 5, step: 0.1 },
    ],
  },
  centerline: {
    id: 'centerline',
    defaults: { stroke_width: 0.8, smooth: true, min_branch_px: 3 },
    schema: [
      { key: 'stroke_width', label: 'convert.strokeWidthPx', type: 'number', min: 0.1, max: 5, step: 0.1 },
      { key: 'smooth', label: 'convert.smooth', type: 'boolean' },
      { key: 'min_branch_px', label: 'convert.minBranch', type: 'number', min: 0, max: 50, step: 1 },
    ],
  },
  spiral: {
    id: 'spiral',
    defaults: { spacing_px: 4, samples_per_turn: 64 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'samples_per_turn', label: 'convert.samplesPerTurn', type: 'number', min: 16, max: 256, step: 1 },
    ],
  },
  scanlines: {
    id: 'scanlines',
    defaults: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'wave_amp_px', label: 'convert.waveAmp', type: 'number', min: 0, max: 20, step: 0.5 },
      { key: 'wave_period_px', label: 'convert.wavePeriod', type: 'number', min: 2, max: 50, step: 0.5 },
    ],
  },
  tsp: {
    id: 'tsp',
    defaults: { density: 0.02, seed: 0 },
    schema: [
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
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
// Styles (merger of monoModes.ts + printStyles.ts)
// =====================================================================

export type StyleScope = 'master' | 'layer'
export type PrintStyleKind = 'image' | 'schematic' | 'text'
export type SegmentationMethod = 'kmeans' | 'luminance_bands' | 'thresholds' | 'fixed_palette'

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
  default_num_bands?: number      // luminance_bands
  default_threshold?: number      // thresholds (single split → binary)
  default_num_colors?: number     // kmeans
  drop_background: boolean
  background_luminance: number
  // When true, the UI exposes a bands slider for this style (mainly
  // shaded modes). Binary modes hide it.
  knob_bands: boolean
}

export interface PrintStyle {
  id: string
  labelKey: string
  descriptionKey?: string
  applicableTo: PrintStyleKind[]
  scope: StyleScope

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
}

// Helper: linear interpolation across band index for spacing / density
// recipes. ``i`` 0..total-1, returns ``from`` at i=0 and ``to`` at
// i=total-1 (or ``from`` if total<=1).
function lerp(i: number, total: number, from: number, to: number): number {
  if (total <= 1) return from
  return from + (to - from) * (i / (total - 1))
}

// Naming convention to resolve old collisions between mono modes and
// per-layer presets:
//   - master shaded photo modes keep simple ids: pencil, halftone-shade,
//     stippling-shade, engraving, contours-topo
//   - master binary modes: outline, tsp, spiral-master
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
    segmentation: {
      method: 'luminance_bands',
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
    segmentation: {
      method: 'luminance_bands',
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
    segmentation: {
      method: 'luminance_bands',
      default_num_bands: 1,
      drop_background: true,
      background_luminance: 0.85,
      knob_bands: true,
    },
    defaultAlgorithm: 'stippling',
    defaultAlgorithmOptions: { density: 0.03, dot_radius_px: 0.5, seed: 0 },
    bandRecipe(i, total) {
      const density = lerp(i, total, 0.06, 0.012)
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
    segmentation: {
      method: 'luminance_bands',
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
    segmentation: {
      method: 'luminance_bands',
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
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
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
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
    },
    defaultAlgorithm: 'spiral',
    defaultAlgorithmOptions: { spacing_px: 3, samples_per_turn: 64 },
    bandRecipe() {
      return { algorithm: 'spiral', algorithm_options: { spacing_px: 3, samples_per_turn: 64 } }
    },
  },
  {
    id: 'centerline-trace',
    labelKey: 'mono.modes.centerline',
    descriptionKey: 'mono.modes.centerlineDesc',
    applicableTo: ['image', 'schematic'],
    scope: 'master',
    segmentation: {
      method: 'thresholds',
      default_threshold: 0.5,
      drop_background: true,
      background_luminance: 0.55,
      knob_bands: false,
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
]

// Default master style applied when the operator first switches to
// monochrome — pencil is the friendliest general-purpose choice for
// photographs.
export const DEFAULT_MASTER_STYLE_ID = 'pencil'

// Old monoModes ids that the rehydration path may encounter on saved
// placements / variants. Maps them to their new registry id so existing
// state doesn't silently break.
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
