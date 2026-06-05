// Curated 12-style catalogue for the beginner editor's
// "Personnaliser le style" panel.
//
// The full registry ships 27 algorithms (frontend/src/data/printRegistry.ts)
// — most have a niche use case or are surfaced automatically by the
// resolver for specific source kinds (text → hershey, pdf → pdf_text_*).
// Exposing all of them to a beginner is overwhelming, so we hand-pick a
// dozen with clear visual identities, sensible defaults, and a single
// dominant knob that maps cleanly to a 1-line slider.
//
// The IDs match the backend algorithm names exactly (no aliasing), so
// emitted ``PolicyPass`` entries flow straight through to the existing
// /rerender pipeline. The primary knob's ``optionKey`` is the registry
// schema key the slider writes to; the unused options keep their backend
// defaults from ``printRegistry.ts``.

import type { AlgorithmId } from '../../data/printRegistry'

export interface BeginnerStyleKnob {
  /** Registry option key the slider writes to (e.g. ``spacing_px``). */
  optionKey: string
  /** i18n key for the knob's user-facing label. */
  labelKey: string
  min: number
  max: number
  step: number
  default: number
  /** Optional suffix shown after the value (``px``, ``°``, …). */
  unit?: string
}

export interface BeginnerStyle {
  id: AlgorithmId
  /** Single-character icon shown on the chip. */
  icon: string
  /** i18n key for the style's display name (``v2.style.<id>``). */
  labelKey: string
  /** The one knob exposed to the beginner. Per the design decision
   *  frozen 2026-06-05, each style surfaces exactly one slider. */
  primaryKnob: BeginnerStyleKnob
}

/** Hard cap on stacked styles. Larger stacks slow the preview down and
 *  rarely produce intelligible results for a beginner — the resolver's
 *  built-in multi-pass for QUALITY tier already covers the "more is
 *  more" use case automatically. */
export const MAX_BEGINNER_STYLES = 4

export const BEGINNER_STYLES: readonly BeginnerStyle[] = [
  {
    id: 'crosshatch',
    icon: '▥',
    labelKey: 'v2.style.crosshatch',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 4,
      unit: 'px',
    },
  },
  {
    id: 'scanlines',
    icon: '〰',
    labelKey: 'v2.style.scanlines',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 4,
      unit: 'px',
    },
  },
  {
    id: 'stippling',
    icon: '⠁',
    labelKey: 'v2.style.stippling',
    primaryKnob: {
      optionKey: 'density',
      labelKey: 'convert.density',
      min: 0.001,
      max: 0.5,
      step: 0.001,
      default: 0.02,
    },
  },
  {
    id: 'voronoi_stipple',
    icon: '⠿',
    labelKey: 'v2.style.voronoiStipple',
    primaryKnob: {
      optionKey: 'density',
      labelKey: 'convert.density',
      min: 0.001,
      max: 0.5,
      step: 0.001,
      default: 0.02,
    },
  },
  {
    id: 'halftone',
    icon: '⬢',
    labelKey: 'v2.style.halftone',
    primaryKnob: {
      optionKey: 'cell_size_px',
      labelKey: 'convert.cellSize',
      min: 1,
      max: 64,
      step: 1,
      default: 6,
      unit: 'px',
    },
  },
  {
    id: 'grid',
    icon: '▦',
    labelKey: 'v2.style.grid',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 6,
      unit: 'px',
    },
  },
  {
    id: 'spiral',
    icon: '◯',
    labelKey: 'v2.style.spiral',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 4,
      unit: 'px',
    },
  },
  {
    id: 'rings',
    icon: '⊙',
    labelKey: 'v2.style.rings',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 6,
      unit: 'px',
    },
  },
  {
    id: 'sunburst',
    icon: '☀',
    labelKey: 'v2.style.sunburst',
    primaryKnob: {
      optionKey: 'rays',
      labelKey: 'convert.rays',
      min: 8,
      max: 720,
      step: 4,
      default: 120,
    },
  },
  {
    id: 'circle_pack',
    icon: '◌',
    labelKey: 'v2.style.circlePack',
    primaryKnob: {
      optionKey: 'max_radius_px',
      labelKey: 'convert.maxRadius',
      min: 1,
      max: 40,
      step: 0.5,
      default: 7,
      unit: 'px',
    },
  },
  {
    id: 'scribble',
    icon: '✎',
    labelKey: 'v2.style.scribble',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 4,
      unit: 'px',
    },
  },
  {
    id: 'squiggle',
    icon: '⌇',
    labelKey: 'v2.style.squiggle',
    primaryKnob: {
      optionKey: 'spacing_px',
      labelKey: 'convert.spacing',
      min: 1,
      max: 30,
      step: 0.5,
      default: 4,
      unit: 'px',
    },
  },
]

/** O(1) lookup helper for the modal's render loops. */
const STYLE_BY_ID = new Map<AlgorithmId, BeginnerStyle>(
  BEGINNER_STYLES.map((s) => [s.id, s]),
)

export function getBeginnerStyle(id: AlgorithmId): BeginnerStyle | undefined {
  return STYLE_BY_ID.get(id)
}
