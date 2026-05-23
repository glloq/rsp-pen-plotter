// Per-algorithm option schemas: each entry is the set of knobs the
// backend's renderer accepts, plus their defaults. The schema drives the
// inline form rendered next to the algorithm selector wherever
// algorithm options are editable (LayerCard's "Advanced" drawer and
// PassList's per-pass parameter panel).
//
// Keys / ranges mirror the algorithm signatures in
// ``backend/pen_plotter/converters/algorithms/*.py``. If a new
// algorithm is added there, add it here too so both the single-style
// picker and the multi-pass editor surface the right knobs.

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

export interface AlgoSpec {
  defaults: Record<string, unknown>
  schema: AlgoOption[]
}

export const ALGO_OPTIONS: Record<string, AlgoSpec> = {
  direct: { defaults: {}, schema: [] },
  halftone: {
    defaults: { cell_size_px: 6 },
    schema: [
      { key: 'cell_size_px', label: 'convert.cellSize', type: 'number', min: 1, max: 64, step: 1 },
    ],
  },
  stippling: {
    defaults: { density: 0.02, dot_radius_px: 0.6, seed: 0 },
    schema: [
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'dot_radius_px', label: 'convert.dotRadius', type: 'number', min: 0.1, max: 5, step: 0.1 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  crosshatch: {
    defaults: { angle_deg: 45, spacing_px: 4, crossed: false },
    schema: [
      { key: 'angle_deg', label: 'convert.angleDeg', type: 'number', min: 0, max: 180, step: 1 },
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'crossed', label: 'convert.crossed', type: 'boolean' },
    ],
  },
  contours: {
    defaults: { spacing_px: 4, max_rings: 20 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'max_rings', label: 'convert.maxRings', type: 'number', min: 1, max: 100, step: 1 },
    ],
  },
  edges: {
    defaults: { stroke_width: 0.8 },
    schema: [
      { key: 'stroke_width', label: 'convert.strokeWidthPx', type: 'number', min: 0.1, max: 5, step: 0.1 },
    ],
  },
  spiral: {
    defaults: { spacing_px: 4, samples_per_turn: 64 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'samples_per_turn', label: 'convert.samplesPerTurn', type: 'number', min: 16, max: 256, step: 1 },
    ],
  },
  scanlines: {
    defaults: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'wave_amp_px', label: 'convert.waveAmp', type: 'number', min: 0, max: 20, step: 0.5 },
      { key: 'wave_period_px', label: 'convert.wavePeriod', type: 'number', min: 2, max: 50, step: 0.5 },
    ],
  },
  tsp: {
    defaults: { density: 0.02, seed: 0 },
    schema: [
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
}

export function getAlgoSpec(name: string | null | undefined): AlgoSpec | null {
  if (!name) return null
  return ALGO_OPTIONS[name] ?? null
}

export function defaultsFor(name: string): Record<string, unknown> {
  return { ...(ALGO_OPTIONS[name]?.defaults ?? {}) }
}
