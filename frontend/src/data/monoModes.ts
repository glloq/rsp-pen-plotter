// Monochrome rendering modes — recipes that combine a segmentation
// strategy with per-band algorithm choices to produce a recognisable
// visual style with a single pen. A mode owns:
//   - which segmentation to use at /upload time (luminance bands for
//     shaded modes, thresholds for binary modes)
//   - the uniform algorithm used during /upload (so the converter has
//     something sensible to render with even before /rerender refines)
//   - a function that, once the layers are known, returns per-band
//     algorithm overrides applied via /rerender — this is how the
//     darkest band gets denser dots than the lightest, or how each
//     crosshatch band uses a different angle, without baking it into
//     the segmentation.
//
// The user picks ONE mode in MonochromeCard. SourceSection applies
// the segmentation + algorithm pre-upload, then calls
// store.applyLayerAlgorithm for every produced layer to install the
// per-band override. A single debounced /rerender fires once all
// overrides are queued.

export type SegmentationMethodMono = 'luminance_bands' | 'thresholds'

export interface MonoBandOverride {
  algorithm: string
  algorithm_options: Record<string, unknown>
}

export interface MonoMode {
  id: string
  labelKey: string
  descKey: string
  // ------- /upload-time segmentation + uniform algo -------
  segmentation_method: SegmentationMethodMono
  // For luminance_bands. ``default_bands`` is the operator-facing
  // default; the actual count can be overridden via the bands slider
  // shown in MonochromeCard when ``knob_bands`` is true.
  default_bands: number
  // For thresholds (binary modes). Defaults to a single mid-grey
  // split that yields one dark + one light band; the light band is
  // dropped via drop_background so we end up with one rendered layer.
  default_threshold: number
  default_algorithm: string
  // Uniform algorithm options used at /upload time. Per-band overrides
  // applied via /rerender are independent.
  default_algorithm_options: Record<string, unknown>
  drop_background: boolean
  background_luminance: number
  // UI affordances the mode exposes. When ``knob_bands`` is false the
  // slider is hidden (binary / single-layer modes don't need it).
  knob_bands: boolean
  // Compute the per-band override for a band at index ``i`` out of
  // ``total`` rendered layers (already ordered darkest-first by the
  // backend). Returning null keeps the upload-time default.
  algoForBand: (i: number, total: number) => MonoBandOverride | null
}

// Helper: linear interpolation across band index for spacing / density
// recipes. ``i`` 0..total-1, returns ``from`` at i=0 and ``to`` at
// i=total-1 (or ``from`` if total<=1).
function lerp(i: number, total: number, from: number, to: number): number {
  if (total <= 1) return from
  return from + (to - from) * (i / (total - 1))
}

export const MONO_MODES: MonoMode[] = [
  // -------------------- SHADED PHOTO MODES --------------------
  {
    id: 'pencil',
    labelKey: 'mono.modes.pencil',
    descKey: 'mono.modes.pencilDesc',
    segmentation_method: 'luminance_bands',
    default_bands: 4,
    default_threshold: 0.5,
    default_algorithm: 'crosshatch',
    default_algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: false },
    drop_background: true,
    background_luminance: 0.85,
    knob_bands: true,
    // Darkest = densest crossed hatching; lighter bands = single
    // direction at progressively larger spacing and rotating angles
    // for the classic layered-pencil look.
    algoForBand(i, total) {
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
    id: 'halftone',
    labelKey: 'mono.modes.halftone',
    descKey: 'mono.modes.halftoneDesc',
    segmentation_method: 'luminance_bands',
    default_bands: 4,
    default_threshold: 0.5,
    default_algorithm: 'halftone',
    default_algorithm_options: { cell_size_px: 5 },
    drop_background: true,
    background_luminance: 0.85,
    knob_bands: true,
    // Newspaper-style: cell size grows with band index so the darkest
    // band has the tightest dot grid (looks dense, lots of ink) and
    // lighter bands have coarser dots (looks sparse).
    algoForBand(i, total) {
      const cell = lerp(i, total, 3, 9)
      return {
        algorithm: 'halftone',
        algorithm_options: { cell_size_px: cell },
      }
    },
  },
  {
    id: 'stippling',
    labelKey: 'mono.modes.stippling',
    descKey: 'mono.modes.stipplingDesc',
    segmentation_method: 'luminance_bands',
    default_bands: 4,
    default_threshold: 0.5,
    default_algorithm: 'stippling',
    default_algorithm_options: { density: 0.03, dot_radius_px: 0.5, seed: 0 },
    drop_background: true,
    background_luminance: 0.85,
    knob_bands: true,
    // Portrait stippling: density highest in darkest band, decays for
    // lighter bands so we get a tonal gradient of dot scatter.
    algoForBand(i, total) {
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
    descKey: 'mono.modes.engravingDesc',
    segmentation_method: 'luminance_bands',
    default_bands: 3,
    default_threshold: 0.5,
    default_algorithm: 'scanlines',
    default_algorithm_options: { spacing_px: 3, wave_amp_px: 0, wave_period_px: 12 },
    drop_background: true,
    background_luminance: 0.85,
    knob_bands: true,
    // Banknote / passport-style engraving: scanline spacing grows for
    // lighter bands. Add a small sinusoidal wave for the
    // distinctive "guilloche" feel.
    algoForBand(i, total) {
      const spacing = lerp(i, total, 1.8, 5)
      const wave = lerp(i, total, 0.6, 1.6)
      return {
        algorithm: 'scanlines',
        algorithm_options: { spacing_px: spacing, wave_amp_px: wave, wave_period_px: 14 },
      }
    },
  },
  {
    id: 'contours',
    labelKey: 'mono.modes.contours',
    descKey: 'mono.modes.contoursDesc',
    segmentation_method: 'luminance_bands',
    default_bands: 4,
    default_threshold: 0.5,
    default_algorithm: 'contours',
    default_algorithm_options: { spacing_px: 4, max_rings: 20 },
    drop_background: true,
    background_luminance: 0.85,
    knob_bands: true,
    // Topographic-map look: tighter contour spacing for darker bands.
    algoForBand(i, total) {
      const spacing = lerp(i, total, 2.5, 6)
      const rings = Math.round(lerp(i, total, 30, 10))
      return {
        algorithm: 'contours',
        algorithm_options: { spacing_px: spacing, max_rings: rings },
      }
    },
  },
  // -------------------- BINARY / SINGLE-LINE MODES --------------------
  {
    id: 'outline',
    labelKey: 'mono.modes.outline',
    descKey: 'mono.modes.outlineDesc',
    segmentation_method: 'thresholds',
    default_bands: 2,
    default_threshold: 0.5,
    default_algorithm: 'edges',
    default_algorithm_options: { stroke_width: 0.8 },
    drop_background: true,
    background_luminance: 0.55,
    knob_bands: false,
    // Single rendered layer — outline only, no fill. Perfect for
    // logos, signs, simple line art.
    algoForBand() {
      return { algorithm: 'edges', algorithm_options: { stroke_width: 0.8 } }
    },
  },
  {
    id: 'tsp',
    labelKey: 'mono.modes.tsp',
    descKey: 'mono.modes.tspDesc',
    segmentation_method: 'thresholds',
    default_bands: 2,
    default_threshold: 0.5,
    default_algorithm: 'tsp',
    default_algorithm_options: { density: 0.04, seed: 0 },
    drop_background: true,
    background_luminance: 0.55,
    knob_bands: false,
    // Single-line art: every "ink" pixel of the binarised image is a
    // node, connected by a nearest-neighbour tour. Looks like a
    // continuous doodle.
    algoForBand() {
      return { algorithm: 'tsp', algorithm_options: { density: 0.04, seed: 0 } }
    },
  },
  {
    id: 'spiral',
    labelKey: 'mono.modes.spiral',
    descKey: 'mono.modes.spiralDesc',
    segmentation_method: 'thresholds',
    default_bands: 2,
    default_threshold: 0.5,
    default_algorithm: 'spiral',
    default_algorithm_options: { spacing_px: 3, samples_per_turn: 64 },
    drop_background: true,
    background_luminance: 0.55,
    knob_bands: false,
    // Single Archimedean spiral clipped to the dark region of the
    // binarised image. Visually striking; great for portraits with
    // strong contrast.
    algoForBand() {
      return { algorithm: 'spiral', algorithm_options: { spacing_px: 3, samples_per_turn: 64 } }
    },
  },
]

export function getMonoMode(id: string): MonoMode | undefined {
  return MONO_MODES.find((m) => m.id === id)
}

// Default mode used when the operator first switches to monochrome —
// pencil is the friendliest general-purpose choice for photographs.
export const DEFAULT_MONO_MODE = 'pencil'
