// Declarative knob descriptors for the master-style params cards.
//
// Before this module existed, ``MasterStyleParams.vue`` (mono) and
// ``MultiColorMasterStyleParams.vue`` (colour) each hard-coded one
// template block per master style — every new algorithm batch meant
// hand-editing both twins. The per-style UI now lives here as data and
// a single generic renderer (``MasterStyleKnobs.vue``) draws it; a new
// style added to ``printRegistry`` needs an entry here (or none, in
// which case the schema-driven ``AlgoParamsForm`` fallback renders its
// algorithm's full option set) and ZERO component edits.
//
// Conventions, inherited from the old hand-built blocks:
//   * ``dual-range`` edits a ``*_min``/``*_max`` knob pair that the
//     recipe lerps across bands/clusters (dark → light).
//   * ``range``/``checkbox`` edit a single global knob.
//   * ``angle-set`` is the hatch-family angle chip picker.
//   * Bounds/steps are the operator-facing *slider* bounds. They are
//     intentionally narrower than the raw ``ALGORITHMS`` schema bounds
//     (the Layers tab's expert form): the master cards expose a compact
//     "safe" range per style, so the numbers live here, not in
//     ``AlgoOption``. Knob keys (``spacing_min``…) are recipe inputs,
//     not algorithm option keys, so there is nothing to dedupe against.
//   * Current values come from the draft's knob store, falling back to
//     ``MONO_STYLE_DEFAULTS`` / ``MULTICOLOR_STYLE_DEFAULTS`` — the
//     test suite asserts every key referenced here exists in those
//     defaults so the fallback chain always terminates.

import { MONO_STYLE_DEFAULTS, MULTICOLOR_STYLE_DEFAULTS } from './printRegistry'

export interface DualRangeKnob {
  kind: 'dual-range'
  keyMin: string
  keyMax: string
  min: number
  max: number
  step: number
  /** DualRangeSlider unit suffix (the component inserts the space). */
  unit?: string
  labelKey: string
  hintKey?: string
}

export interface RangeKnob {
  kind: 'range'
  key: string
  min: number
  max: number
  step: number
  labelKey: string
  hintKey?: string
  /** Decimal places for the value readout; omitted → ``Math.round``. */
  decimals?: number
  /** Readout suffix, verbatim (``' px'``, ``'°'``, ``' s'``). */
  unit?: string
  /** Render the readout as ``Math.round(v * 100)%`` (0..1 knobs). */
  percent?: boolean
}

export interface CheckboxKnob {
  kind: 'checkbox'
  key: string
  labelKey: string
}

export interface AngleSetKnob {
  kind: 'angle-set'
  key: string
  choices: readonly number[]
  /** Chip picker keeps 1..maxSelected angles active. */
  maxSelected: number
  labelKey: string
  hintKey?: string
}

export type KnobDescriptor = DualRangeKnob | RangeKnob | CheckboxKnob | AngleSetKnob

export interface StyleKnobConfig {
  /** Explanatory paragraph rendered above the controls. */
  introHintKey?: string
  /**
   * Rendered *instead of* controls — for styles that intentionally have
   * no tunable knobs (flat aplats). Distinct from "no config at all",
   * which falls back to the schema-driven AlgoParamsForm.
   */
  placeholderKey?: string
  controls: KnobDescriptor[]
}

export type MasterStyleFamily = 'mono' | 'multicolor'

// ---- Terse builders (data below stays one-line-per-control) ----

function dual(
  keyMin: string,
  keyMax: string,
  min: number,
  max: number,
  step: number,
  labelKey: string,
  extra: Partial<Pick<DualRangeKnob, 'unit' | 'hintKey'>> = {},
): DualRangeKnob {
  return { kind: 'dual-range', keyMin, keyMax, min, max, step, labelKey, ...extra }
}

function range(
  key: string,
  min: number,
  max: number,
  step: number,
  labelKey: string,
  extra: Partial<Pick<RangeKnob, 'decimals' | 'unit' | 'percent' | 'hintKey'>> = {},
): RangeKnob {
  return { kind: 'range', key, min, max, step, labelKey, ...extra }
}

function checkbox(key: string, labelKey: string): CheckboxKnob {
  return { kind: 'checkbox', key, labelKey }
}

// ---- Shared blocks (styles that expose identical knob sets) ----

// Pencil / hatch-fill / scribble: angle chips + spacing range + crossed.
const HATCH_FAMILY: StyleKnobConfig = {
  controls: [
    {
      kind: 'angle-set',
      key: 'angles',
      choices: [0, 30, 45, 90, 135, 150],
      maxSelected: 4,
      labelKey: 'mono.angles',
      hintKey: 'mono.anglesHint',
    },
    dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', {
      unit: 'mm',
      hintKey: 'mono.spacingRangeHint',
    }),
    checkbox('crossed_on_darkest', 'mono.crossedOnDarkest'),
  ],
}

const DOT_RADIUS = range('dot_radius', 0.11, 0.56, 0.1, 'mono.dotRadius', { decimals: 2 })
const STROKE_WIDTH = range('stroke_width', 0.4, 2.0, 0.1, 'mono.strokeWidth', { decimals: 2 })

// Stippling / Voronoi shade: density range + dot radius.
const STIPPLE_MONO: StyleKnobConfig = {
  controls: [
    dual('density_min', 'density_max', 0.005, 0.5, 0.002, 'mono.densityRange', {
      hintKey: 'mono.densityRangeHint',
    }),
    DOT_RADIUS,
  ],
}

// Engraving / squiggle: spacing range + wave amplitude range + period.
const ENGRAVE: StyleKnobConfig = {
  controls: [
    dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
    dual('wave_min', 'wave_max', 0, 1.1, 0.1, 'mono.waveRange', { unit: 'mm' }),
    range('wave_period', 3, 7.4, 0.1, 'mono.wavePeriod', { decimals: 1, unit: ' mm' }),
  ],
}

// Flow-field / Hilbert: spacing range only (gosper-fill intentionally
// has no entry — its tone is the L-system order lerped by the registry
// bandRecipe, so it renders the generic AlgoParamsForm fallback).
const SPACING_WIDE: StyleKnobConfig = {
  controls: [
    dual('spacing_min', 'spacing_max', 0.37, 7.4, 0.1, 'mono.spacingRange', {
      unit: 'mm',
      hintKey: 'mono.spacingRangeHint',
    }),
  ],
}

// TSP / TSP-optimised: dot density (single knob — binary mono).
const DOT_DENSITY: StyleKnobConfig = {
  controls: [
    range('density', 0.01, 0.1, 0.005, 'mono.dotDensity', {
      decimals: 3,
      hintKey: 'mono.dotDensityHint',
    }),
  ],
}

// Outline / centerline: stroke width (binary mono).
const STROKE_ONLY: StyleKnobConfig = { controls: [STROKE_WIDTH] }

// ---- Monochrome master family ----

export const MONO_STYLE_KNOBS: Record<string, StyleKnobConfig> = {
  pencil: HATCH_FAMILY,
  'hatch-fill': HATCH_FAMILY,
  scribble: HATCH_FAMILY,
  'halftone-shade': {
    controls: [
      dual('cell_min', 'cell_max', 0.74, 5.2, 0.1, 'mono.cellRange', {
        unit: 'mm',
        hintKey: 'mono.cellRangeHint',
      }),
    ],
  },
  'stippling-shade': STIPPLE_MONO,
  'voronoi-shade': STIPPLE_MONO,
  engraving: ENGRAVE,
  'squiggle-shade': ENGRAVE,
  'contours-topo': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      dual('rings_min', 'rings_max', 5, 40, 1, 'mono.ringsRange', {
        hintKey: 'mono.ringsRangeHint',
      }),
    ],
  },
  'concentric-rings': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      dual('rings_min', 'rings_max', 2, 80, 1, 'mono.ringsRange', {
        hintKey: 'mono.ringsRangeHint',
      }),
    ],
  },
  lowpoly: {
    controls: [
      dual('density_min', 'density_max', 0.002, 0.1, 0.002, 'mono.densityRange', {
        hintKey: 'mono.densityRangeHint',
      }),
    ],
  },
  'flowfield-master': SPACING_WIDE,
  'hilbert-fill': SPACING_WIDE,
  tsp: DOT_DENSITY,
  'tsp-optimized': DOT_DENSITY,
  'spiral-master': {
    introHintKey: 'mono.spiralTonalHint',
    controls: [
      range('spacing_mm', 1.1, 11, 0.1, 'mono.spiralSpacing', {
        unit: ' mm',
        hintKey: 'mono.spiralSpacingHint',
      }),
      range('wavelength_mm', 0.74, 8.9, 0.1, 'mono.spiralWavelength', {
        unit: ' mm',
        hintKey: 'mono.spiralWavelengthHint',
      }),
      range('tone_strength', 0, 1, 0.05, 'mono.spiralStrength', {
        percent: true,
        hintKey: 'mono.spiralStrengthHint',
      }),
    ],
  },
  outline: STROKE_ONLY,
  'centerline-trace': STROKE_ONLY,
  // Phase-2 banded patterns (2026-06): each dual range drives the
  // dark→light lerp of the style's tonal knob; conventions mirror the
  // colour twins (color-truchet, color-rings, color-sunburst, …).
  'truchet-tiles': {
    controls: [dual('cell_min', 'cell_max', 0.74, 11, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'maze-walk': {
    controls: [dual('cell_min', 'cell_max', 1.5, 7.4, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'basket-weave': {
    controls: [dual('band_min', 'band_max', 1.5, 11, 0.1, 'convert.bandPx', { unit: 'mm' })],
  },
  'stitch-rows': {
    controls: [dual('cell_min', 'cell_max', 1.5, 7.4, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'bubble-pack': {
    controls: [
      dual('radius_min', 'radius_max', 0.74, 7.4, 0.1, 'colorStyles.radiusRange', {
        unit: 'mm',
        hintKey: 'colorStyles.radiusRangeHint',
      }),
      range('gap_mm', 0, 2.2, 0.1, 'convert.gapPx', { decimals: 1, unit: ' mm' }),
    ],
  },
  'brick-courses': {
    controls: [dual('cell_min', 'cell_max', 0.74, 11, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'dash-shading': {
    controls: [
      {
        kind: 'angle-set',
        key: 'angles',
        choices: [0, 30, 45, 90, 135, 150],
        maxSelected: 4,
        labelKey: 'mono.angles',
        hintKey: 'mono.anglesHint',
      },
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('dash_mm', 0.19, 4.5, 0.1, 'convert.dashPx', { decimals: 1, unit: ' mm' }),
    ],
  },
  'vinyl-rings': {
    controls: [dual('spacing_min', 'spacing_max', 0.37, 7.4, 0.1, 'mono.spacingRange', { unit: 'mm' })],
  },
  'sunburst-rays': {
    controls: [
      dual('rays_min', 'rays_max', 8, 360, 4, 'colorStyles.raysRange', {
        hintKey: 'colorStyles.raysRangeHint',
      }),
    ],
  },
  'thread-fans': {
    controls: [
      dual('cell_min', 'cell_max', 2.2, 11, 0.1, 'mono.cellRange', { unit: 'mm' }),
      range('chords', 3, 12, 1, 'convert.chords'),
    ],
  },
  'moire-beat': {
    controls: [dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' })],
  },
  'penrose-facets': {
    controls: [range('divisions', 4, 8, 1, 'convert.divisions')],
  },
}

// ---- Multicolour master family ----

// Flat aplats: no tunable knobs, just an explanatory placeholder.
const FLAT_PLACEHOLDER: StyleKnobConfig = {
  placeholderKey: 'colorStyles.flatNoKnobs',
  controls: [],
}

// Density range shared by the colour stipple / TSP families.
const DENSITY_COLOR = (hintKey?: string): DualRangeKnob =>
  dual('density_min', 'density_max', 0.005, 0.3, 0.001, 'mono.densityRange', { hintKey })

export const MULTICOLOR_STYLE_KNOBS: Record<string, StyleKnobConfig> = {
  'color-flat': FLAT_PLACEHOLDER,
  'color-flat-lab': FLAT_PLACEHOLDER,
  'color-crosshatch': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', {
        unit: 'mm',
        hintKey: 'colorStyles.crosshatchSpacingHint',
      }),
      range('angle_step', 0, 90, 5, 'colorStyles.angleStep', {
        unit: '°',
        hintKey: 'colorStyles.angleStepHint',
      }),
      checkbox('crossed', 'convert.crossed'),
    ],
  },
  'color-stipple': {
    controls: [
      DENSITY_COLOR(),
      DOT_RADIUS,
      range('iterations', 0, 20, 1, 'convert.iterations', {
        hintKey: 'colorStyles.iterationsHint',
      }),
    ],
  },
  'color-halftone-cmyk': {
    controls: [
      range('cell_size', 0.74, 5.2, 0.1, 'convert.cellSize', {
        unit: ' mm',
        hintKey: 'colorStyles.cmykHint',
      }),
    ],
  },
  'color-contours-topo': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      dual('rings_min', 'rings_max', 5, 40, 1, 'mono.ringsRange'),
    ],
  },
  'color-flowfield': {
    controls: [
      dual('seed_spacing_min', 'seed_spacing_max', 0.74, 11, 0.1, 'colorStyles.seedSpacingRange', {
        unit: 'mm',
        hintKey: 'colorStyles.seedSpacingHint',
      }),
      range('step_mm', 0.07, 1.1, 0.1, 'convert.stepPx', { decimals: 1, unit: ' mm' }),
      range('max_steps', 100, 2000, 50, 'convert.maxSteps'),
      range('noise_scale', 4, 128, 2, 'convert.noiseScale'),
      checkbox('bidirectional', 'convert.bidirectional'),
    ],
  },
  'color-sketch': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      dual('amp_min', 'amp_max', 0.07, 1.5, 0.1, 'colorStyles.ampRange', { unit: 'mm' }),
      range('period_mm', 0.74, 7.4, 0.1, 'mono.wavePeriod', { decimals: 1, unit: ' mm' }),
      range('jitter', 0, 1, 0.05, 'convert.jitter', { decimals: 2 }),
    ],
  },
  'color-spiral': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('max_rings', 5, 120, 1, 'convert.maxRings'),
    ],
  },
  'color-stippling-classic': {
    controls: [DENSITY_COLOR(), DOT_RADIUS],
  },
  'color-edges': { controls: [STROKE_WIDTH] },
  'color-centerline': {
    controls: [STROKE_WIDTH, range('min_branch_mm', 0.37, 7.4, 0.1, 'convert.minBranch', { decimals: 1, unit: ' mm' })],
  },
  'color-spiral-classic': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('samples_per_turn', 16, 256, 4, 'convert.samplesPerTurn'),
    ],
  },
  'color-scanlines': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('wave_amp_mm', 0, 2.2, 0.1, 'convert.waveAmp', { decimals: 1, unit: ' mm' }),
      range('wave_period_mm', 0.74, 15, 0.1, 'convert.wavePeriod', { decimals: 1, unit: ' mm' }),
    ],
  },
  'color-tsp': {
    controls: [DENSITY_COLOR('colorStyles.tspHint')],
  },
  'color-hilbert': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('min_run_mm', 0.37, 7.4, 0.1, 'convert.minRunPx', { decimals: 1, unit: ' mm' }),
    ],
  },
  'color-gosper': {
    controls: [
      range('order', 1, 6, 1, 'convert.gosperOrder', { hintKey: 'colorStyles.gosperOrderHint' }),
      dual('spacing_min', 'spacing_max', 0.37, 3, 0.1, 'mono.spacingRange', { unit: 'mm' }),
    ],
  },
  'color-eulerian': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('angle_step', 0, 90, 5, 'colorStyles.angleStep', { unit: '°' }),
      checkbox('crossed', 'convert.crossed'),
    ],
  },
  'color-tsp-opt': {
    controls: [
      DENSITY_COLOR(),
      range('max_points', 500, 20000, 500, 'convert.maxPoints'),
      range('time_budget_s', 0.2, 6, 0.1, 'convert.timeBudgetS', { decimals: 1, unit: ' s' }),
    ],
  },
  'color-grid': {
    controls: [dual('spacing_min', 'spacing_max', 0.37, 7.4, 0.1, 'mono.spacingRange', { unit: 'mm' })],
  },
  'color-brick': {
    controls: [dual('cell_min', 'cell_max', 0.74, 11, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'color-dashes': {
    controls: [
      dual('spacing_min', 'spacing_max', 0.37, 3.7, 0.1, 'mono.spacingRange', { unit: 'mm' }),
      range('angle_step', 0, 90, 5, 'colorStyles.angleStep', { unit: '°' }),
      range('dash_mm', 0.19, 4.5, 0.1, 'convert.dashPx', { decimals: 1, unit: ' mm' }),
      range('gap_mm', 0.19, 4.5, 0.1, 'convert.gapPx', { decimals: 1, unit: ' mm' }),
    ],
  },
  'color-truchet': {
    controls: [dual('cell_min', 'cell_max', 0.74, 11, 0.1, 'mono.cellRange', { unit: 'mm' })],
  },
  'color-rings': {
    controls: [dual('spacing_min', 'spacing_max', 0.37, 7.4, 0.1, 'mono.spacingRange', { unit: 'mm' })],
  },
  'color-sunburst': {
    controls: [
      dual('rays_min', 'rays_max', 8, 360, 4, 'colorStyles.raysRange', {
        hintKey: 'colorStyles.raysRangeHint',
      }),
    ],
  },
  'color-circle-pack': {
    controls: [
      dual('radius_min', 'radius_max', 0.74, 7.4, 0.1, 'colorStyles.radiusRange', {
        unit: 'mm',
        hintKey: 'colorStyles.radiusRangeHint',
      }),
      range('gap_mm', 0, 2.2, 0.1, 'convert.gapPx', { decimals: 1, unit: ' mm' }),
    ],
  },
}

// ---- Lookup helpers ----

export function resolveStyleKnobConfig(
  family: MasterStyleFamily,
  styleId: string,
): StyleKnobConfig | undefined {
  return (family === 'mono' ? MONO_STYLE_KNOBS : MULTICOLOR_STYLE_KNOBS)[styleId]
}

/** Registry defaults backing the knob store for one style. */
export function styleKnobDefaults(
  family: MasterStyleFamily,
  styleId: string,
): Record<string, unknown> {
  return (family === 'mono' ? MONO_STYLE_DEFAULTS : MULTICOLOR_STYLE_DEFAULTS)[styleId] ?? {}
}

/** Knob-store keys a descriptor reads/writes (dual-range → two). */
export function knobKeys(d: KnobDescriptor): string[] {
  return d.kind === 'dual-range' ? [d.keyMin, d.keyMax] : [d.key]
}
