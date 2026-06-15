// Curated 12-style catalogue for the beginner editor's
// "Personnaliser le style" panel.
//
// The full registry ships 51 algorithms (frontend/src/data/printRegistry.ts)
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
//
// Length knobs are expressed in MILLIMETRES (``spacing_mm``,
// ``cell_size_mm``, ``max_radius_mm``): the backend converts them to
// raster pixels per placement (``convert_mm_options``) using the
// physical footprint shipped with each /rerender, so the on-paper pitch
// the operator dialled in stays constant across page formats — a bigger
// sheet gets proportionally more lines instead of the same drawing
// scaled up. Dimensionless knobs (``density``, ``rays``) stay as-is.

import type { AlgorithmId } from '../../data/printRegistry'

export interface BeginnerStyleKnob {
  /** Registry option key the slider writes to (e.g. ``spacing_mm``). */
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
  /** Single-character glyph kept as a textual fallback (assistive
   *  technology + low-bandwidth contexts). The chip renders the
   *  ``thumbnailSvg`` visually. */
  icon: string
  /** Inline SVG ``<path>`` markup (without the outer ``<svg>`` wrapper)
   *  that illustrates the style at a glance — solves the
   *  "▥ vs ⠿ vs ⊙ — what does this *do*?" problem for beginners who
   *  have never seen the algorithm's output. Drawn in a 24×24 viewbox,
   *  ``currentColor`` for stroke / fill so the chip's active-state
   *  colour propagates. */
  thumbnailSvg: string
  /** i18n key for the style's display name (``v2.style.<id>``). */
  labelKey: string
  /** i18n key for the one-line "what does it produce?" description
   *  shown as a chip tooltip + as a small caption when the style is
   *  selected in the stack. */
  descriptionKey: string
  /** The one knob exposed to the beginner. Per the design decision
   *  frozen 2026-06-05, each style surfaces exactly one slider. */
  primaryKnob: BeginnerStyleKnob
}

/** Hard cap on stacked styles. Larger stacks slow the preview down and
 *  rarely produce intelligible results for a beginner — the resolver's
 *  built-in multi-pass for QUALITY tier already covers the "more is
 *  more" use case automatically. */
export const MAX_BEGINNER_STYLES = 4

// Thumbnails are hand-drawn 24×24 SVG fragments designed to be drawn
// in ``currentColor`` so the chip's active-state colour cascades. They
// favour silhouette over fidelity — a beginner should grasp "ah, that
// one's parallel lines" in under a second, not study brushstrokes.
const TH_CROSSHATCH =
  '<g stroke="currentColor" stroke-width="1.1" fill="none">' +
  '<path d="M2 7 L22 17 M2 12 L22 22 M2 17 L22 27 M2 2 L22 12 M2 -3 L22 7"/>' +
  '<path d="M22 7 L2 17 M22 12 L2 22 M22 17 L2 27 M22 2 L2 12 M22 -3 L2 7" opacity="0.5"/>' +
  '</g>'
const TH_SCANLINES =
  '<g stroke="currentColor" stroke-width="1.1" fill="none">' +
  '<path d="M2 5 H22 M2 9 H22 M2 13 H22 M2 17 H22 M2 21 H22"/>' +
  '</g>'
const TH_STIPPLING =
  '<g fill="currentColor">' +
  '<circle cx="5" cy="4" r="0.9"/><circle cx="11" cy="6" r="0.9"/><circle cx="18" cy="3" r="0.9"/>' +
  '<circle cx="3" cy="10" r="0.9"/><circle cx="9" cy="11" r="0.9"/><circle cx="15" cy="9" r="0.9"/><circle cx="20" cy="13" r="0.9"/>' +
  '<circle cx="6" cy="16" r="0.9"/><circle cx="12" cy="18" r="0.9"/><circle cx="19" cy="19" r="0.9"/>' +
  '<circle cx="4" cy="21" r="0.9"/><circle cx="14" cy="22" r="0.9"/>' +
  '</g>'
const TH_VORONOI =
  '<g fill="currentColor">' +
  '<circle cx="5" cy="5" r="0.9"/><circle cx="12" cy="5" r="0.9"/><circle cx="19" cy="5" r="0.9"/>' +
  '<circle cx="5" cy="12" r="0.9"/><circle cx="12" cy="12" r="0.9"/><circle cx="19" cy="12" r="0.9"/>' +
  '<circle cx="5" cy="19" r="0.9"/><circle cx="12" cy="19" r="0.9"/><circle cx="19" cy="19" r="0.9"/>' +
  '<circle cx="8.5" cy="8.5" r="0.7"/><circle cx="15.5" cy="8.5" r="0.7"/>' +
  '<circle cx="8.5" cy="15.5" r="0.7"/><circle cx="15.5" cy="15.5" r="0.7"/>' +
  '</g>'
const TH_HALFTONE =
  '<g fill="currentColor">' +
  '<circle cx="5" cy="5" r="1.8"/><circle cx="12" cy="5" r="1.2"/><circle cx="19" cy="5" r="0.6"/>' +
  '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="2.2"/><circle cx="19" cy="12" r="1"/>' +
  '<circle cx="5" cy="19" r="0.8"/><circle cx="12" cy="19" r="1.4"/><circle cx="19" cy="19" r="1.9"/>' +
  '</g>'
const TH_GRID =
  '<g stroke="currentColor" stroke-width="1.1" fill="none">' +
  '<path d="M5 2 V22 M12 2 V22 M19 2 V22 M2 5 H22 M2 12 H22 M2 19 H22"/>' +
  '</g>'
const TH_SPIRAL =
  '<path d="M12 12 m-0.5 0 a0.5 0.5 0 1 1 1 0 a1.8 1.8 0 1 1 -3.6 0 a3.1 3.1 0 1 1 6.2 0 a4.4 4.4 0 1 1 -8.8 0 a5.7 5.7 0 1 1 11.4 0 a7 7 0 1 1 -14 0 a8.3 8.3 0 1 1 16.6 0" ' +
  'fill="none" stroke="currentColor" stroke-width="0.9"/>'
const TH_RINGS =
  '<g stroke="currentColor" stroke-width="1" fill="none">' +
  '<circle cx="12" cy="12" r="2"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="11"/>' +
  '</g>'
const TH_SUNBURST =
  '<g stroke="currentColor" stroke-width="1" fill="none">' +
  '<path d="M12 12 L12 2 M12 12 L19 5 M12 12 L22 12 M12 12 L19 19 M12 12 L12 22 M12 12 L5 19 M12 12 L2 12 M12 12 L5 5"/>' +
  '<path d="M12 12 L16 2.5 M12 12 L21.5 8 M12 12 L21.5 16 M12 12 L16 21.5 M12 12 L8 21.5 M12 12 L2.5 16 M12 12 L2.5 8 M12 12 L8 2.5" opacity="0.5"/>' +
  '</g>'
const TH_CIRCLE_PACK =
  '<g stroke="currentColor" stroke-width="0.9" fill="none">' +
  '<circle cx="9" cy="9" r="5"/><circle cx="17" cy="6" r="3"/>' +
  '<circle cx="18" cy="14" r="4"/><circle cx="6" cy="17" r="3.5"/>' +
  '<circle cx="13" cy="19" r="2.5"/><circle cx="3" cy="6" r="2"/>' +
  '</g>'
const TH_SCRIBBLE =
  '<g stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round">' +
  '<path d="M3 5 q3 -2 6 0 t6 0 t6 0"/>' +
  '<path d="M2 10 q4 2 7 0 t6 -1 t7 1"/>' +
  '<path d="M3 15 q3 -2 6 0 t6 1 t6 -1"/>' +
  '<path d="M2 20 q4 2 7 -1 t6 1 t7 0"/>' +
  '</g>'
const TH_SQUIGGLE =
  '<g stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round">' +
  '<path d="M2 6 q2 -3 4 0 t4 0 t4 0 t4 0 t4 0"/>' +
  '<path d="M2 12 q2 -3 4 0 t4 0 t4 0 t4 0 t4 0"/>' +
  '<path d="M2 18 q2 -3 4 0 t4 0 t4 0 t4 0 t4 0"/>' +
  '</g>'

export const BEGINNER_STYLES: readonly BeginnerStyle[] = [
  {
    id: 'crosshatch',
    icon: '▥',
    thumbnailSvg: TH_CROSSHATCH,
    labelKey: 'v2.style.crosshatch',
    descriptionKey: 'v2.style.descCrosshatch',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 1.5,
      unit: 'mm',
    },
  },
  {
    id: 'scanlines',
    icon: '〰',
    thumbnailSvg: TH_SCANLINES,
    labelKey: 'v2.style.scanlines',
    descriptionKey: 'v2.style.descScanlines',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 1.5,
      unit: 'mm',
    },
  },
  {
    id: 'stippling',
    icon: '⠁',
    thumbnailSvg: TH_STIPPLING,
    labelKey: 'v2.style.stippling',
    descriptionKey: 'v2.style.descStippling',
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
    thumbnailSvg: TH_VORONOI,
    labelKey: 'v2.style.voronoiStipple',
    descriptionKey: 'v2.style.descVoronoiStipple',
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
    thumbnailSvg: TH_HALFTONE,
    labelKey: 'v2.style.halftone',
    descriptionKey: 'v2.style.descHalftone',
    primaryKnob: {
      optionKey: 'cell_size_mm',
      labelKey: 'convert.cellSize',
      min: 0.5,
      max: 20,
      step: 0.1,
      default: 2.2,
      unit: 'mm',
    },
  },
  {
    id: 'grid',
    icon: '▦',
    thumbnailSvg: TH_GRID,
    labelKey: 'v2.style.grid',
    descriptionKey: 'v2.style.descGrid',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 2.2,
      unit: 'mm',
    },
  },
  {
    id: 'spiral',
    icon: '◯',
    thumbnailSvg: TH_SPIRAL,
    labelKey: 'v2.style.spiral',
    descriptionKey: 'v2.style.descSpiral',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 1.5,
      unit: 'mm',
    },
  },
  {
    id: 'rings',
    icon: '⊙',
    thumbnailSvg: TH_RINGS,
    labelKey: 'v2.style.rings',
    descriptionKey: 'v2.style.descRings',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 2.2,
      unit: 'mm',
    },
  },
  {
    id: 'sunburst',
    icon: '☀',
    thumbnailSvg: TH_SUNBURST,
    labelKey: 'v2.style.sunburst',
    descriptionKey: 'v2.style.descSunburst',
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
    thumbnailSvg: TH_CIRCLE_PACK,
    labelKey: 'v2.style.circlePack',
    descriptionKey: 'v2.style.descCirclePack',
    primaryKnob: {
      optionKey: 'max_radius_mm',
      labelKey: 'convert.maxRadius',
      min: 0.5,
      max: 15,
      step: 0.1,
      default: 2.6,
      unit: 'mm',
    },
  },
  {
    id: 'scribble',
    icon: '✎',
    thumbnailSvg: TH_SCRIBBLE,
    labelKey: 'v2.style.scribble',
    descriptionKey: 'v2.style.descScribble',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 1.5,
      unit: 'mm',
    },
  },
  {
    id: 'squiggle',
    icon: '⌇',
    thumbnailSvg: TH_SQUIGGLE,
    labelKey: 'v2.style.squiggle',
    descriptionKey: 'v2.style.descSquiggle',
    primaryKnob: {
      optionKey: 'spacing_mm',
      labelKey: 'convert.spacing',
      min: 0.5,
      max: 10,
      step: 0.1,
      default: 1.5,
      unit: 'mm',
    },
  },
]

/** O(1) lookup helper for the modal's render loops. */
const STYLE_BY_ID = new Map<AlgorithmId, BeginnerStyle>(BEGINNER_STYLES.map((s) => [s.id, s]))

export function getBeginnerStyle(id: AlgorithmId): BeginnerStyle | undefined {
  return STYLE_BY_ID.get(id)
}

/** Shared shape used by both ``EditModalV2`` (state) and
 *  ``StyleCustomizer`` (v-model). Single source of truth keeps the
 *  contract symmetrical when the subcomponent emits updates. */
export interface CustomStyleSelection {
  id: AlgorithmId
  /** Live value of the style's single primary knob. Other algorithm
   *  options keep their backend defaults from ``printRegistry.ts``. */
  knobValue: number
}

/** One layer's committed algorithm spec, as stored in
 *  ``placement.layer_algorithms``. Mirrors ``LayerAlgorithm`` from the
 *  job store but kept structural so this module stays store-agnostic
 *  (and trivially unit-testable). */
export interface CommittedLayerSpec {
  algorithm?: string
  algorithm_options?: Record<string, unknown>
  passes?: ReadonlyArray<{
    algorithm: string
    algorithm_options?: Record<string, unknown>
    enabled?: boolean
  }>
}

/**
 * Reconstruct the beginner-editor style stack from a layer's *committed*
 * algorithm spec (``placement.layer_algorithms[layerId]``).
 *
 * Both editor modes ultimately write the same algorithm(s) to every
 * layer (``applyAlgorithmToAllLayers`` / ``applyPassesToAllLayers``), so
 * the committed ``layer_algorithms`` is the single source of truth for
 * what the G-code will draw. The beginner panel, however, starts from an
 * empty stack and lets the policy resolver re-pick — which silently
 * diverges from (and on confirm overwrites) a style the operator already
 * chose. Seeding the stack from the committed spec keeps both modes
 * showing the same style.
 *
 * Returns ``[]`` when the committed style can't be represented with the
 * curated beginner catalogue (an expert-only algorithm outside the 12
 * chips, or no spec at all). The caller then falls back to the resolver,
 * preserving today's default-experience behaviour for those cases.
 */
export function deriveBeginnerStack(
  spec: CommittedLayerSpec | null | undefined,
): CustomStyleSelection[] {
  if (!spec) return []
  // Prefer the multi-pass stack (enabled passes only — disabled ones are
  // a non-destructive UI toggle that never ships). Fall back to the
  // single-algorithm shape.
  const steps: Array<{ algorithm: string; options: Record<string, unknown> }> = []
  if (spec.passes && spec.passes.length) {
    for (const pass of spec.passes) {
      if (pass.enabled === false) continue
      steps.push({ algorithm: pass.algorithm, options: pass.algorithm_options ?? {} })
    }
  } else if (spec.algorithm) {
    steps.push({ algorithm: spec.algorithm, options: spec.algorithm_options ?? {} })
  }
  if (!steps.length) return []

  const stack: CustomStyleSelection[] = []
  for (const step of steps) {
    const style = getBeginnerStyle(step.algorithm as AlgorithmId)
    // Any non-representable step aborts the whole derivation: a partial
    // stack would silently drop passes and mislead the operator about
    // what will be drawn.
    if (!style) return []
    const raw = step.options[style.primaryKnob.optionKey]
    const knobValue =
      typeof raw === 'number' && Number.isFinite(raw) ? raw : style.primaryKnob.default
    stack.push({ id: style.id, knobValue })
    if (stack.length >= MAX_BEGINNER_STYLES) break
  }
  return stack
}
