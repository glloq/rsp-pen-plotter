// Preview-only SVG effects for the V2 editor preview pane.
//
// Extracted from ``EditPreviewPane.vue`` (Phase 4 of the editor audit). Owns
// the two client-side DOM walks the pane applies to the v-html'd SVG:
//
//   1. Per-layer opacity overlay — realises the ink-chip eye toggle + the
//      opacity slider as a *preview* hint (the backend /rerender doesn't
//      consume opacity, so this is what actually hides a colour on screen).
//   2. Display-time stroke floor — keeps hair-thin pens legible at fit zoom
//      without touching the SVG string sent to /generate.
//
// ``previewRoot`` stays declared in the pane (it's the shared template ref for
// both the sheet-bounded and unbounded render surfaces) and is passed in. The
// opacity-map maths is split into the pure ``computeLayerOpacityMap`` below so
// it's testable without a real layout (happy-dom has none).
import { onScopeDispose, watch, type ComputedRef, type Ref } from 'vue'
import { useJobStore } from '../stores/job'
import { applyPreviewStrokeFloor } from '../lib/previewStrokeFloor'

type PreviewMode = 'plot' | 'source' | 'split'

export interface OpacityLayer {
  layer_id: string
  opacity_percent?: number | null
}

/**
 * Build a ``layerId → opacity (0..1)`` map for a single DOM walk instead of N
 * queries. A hidden layer collapses to 0 (the eye toggle); a visible layer
 * uses its clamped ``opacity_percent``. Groups whose layer isn't in this map
 * are reset to 1.0 by the walk so a stale value from a previous SVG can't
 * bleed through.
 */
export function computeLayerOpacityMap(
  layers: OpacityLayer[],
  isVisible: (layerId: string) => boolean,
): Map<string, number> {
  const opacityById = new Map<string, number>()
  for (const layer of layers) {
    const pct = layer.opacity_percent ?? 100
    const visible = isVisible(layer.layer_id)
    opacityById.set(layer.layer_id, visible ? Math.max(0, Math.min(100, pct)) / 100 : 0)
  }
  return opacityById
}

export interface EditorPreviewSvgEffectsDeps {
  /** Shared render-surface ref (the artwork box or the unbounded viewport). */
  previewRoot: Ref<HTMLElement | null>
  /** Active view mode — switching it swaps the displayed SVG, so re-walk. */
  viewMode: Ref<PreviewMode>
  /** Adapted (plot) render SVG getter. */
  plotSvg: () => string | null
  /** Original placement SVG getter. */
  originalSvg: () => string | null
  /** Current zoom factor — changes the on-screen scale → recompute the floor. */
  zoom: Ref<number>
  /** Pane pixel width — same reason as ``zoom``. */
  paneWidth: Ref<number>
  /** Pane pixel height — same reason as ``zoom``. */
  paneHeight: Ref<number>
  /** Artwork box style — its size feeds the on-screen SVG scale. */
  artworkStyle:
    | Ref<{ width: string; height: string } | null>
    | ComputedRef<{ width: string; height: string } | null>
}

// Debounce window for the stroke-floor recompute: wheel-zoom fires per tick
// and a dense SVG walk per tick would stutter; 120 ms after the last change
// is invisible to the operator.
const STROKE_FLOOR_DEBOUNCE_MS = 120

export function useEditorPreviewSvgEffects(deps: EditorPreviewSvgEffectsDeps) {
  const job = useJobStore()

  function applyOpacityOverlay(): void {
    const root = deps.previewRoot.value
    if (!root) return
    const svg = root.querySelector('svg')
    if (!svg) return
    const opacityById = computeLayerOpacityMap(job.layers, (id) => job.isVisible(id))
    // The bitmap / vector / text pipelines all label each per-layer group with
    // ``inkscape:label="color-XXXXXX"`` (= layer_id). The namespaced attribute
    // selector is fragile across parsers (HTML vs XML mode), so we walk every
    // <g> imperatively and filter on the attribute presence. Reset to 1.0 when
    // the group's layer isn't in the active set so a stale value from the
    // previous SVG doesn't bleed through.
    const groups = svg.getElementsByTagName('g')
    for (const g of Array.from(groups)) {
      const label = g.getAttribute('inkscape:label')
      if (!label) continue
      const opacity = opacityById.get(label)
      g.style.opacity = opacity === undefined ? '1' : String(opacity)
    }
  }

  function applyStrokeFloor(): void {
    const root = deps.previewRoot.value
    if (!root) return
    for (const svg of Array.from(root.querySelectorAll('svg'))) {
      const rect = svg.getBoundingClientRect()
      if (!rect.width) continue
      applyPreviewStrokeFloor(svg as SVGSVGElement, rect.width)
    }
  }

  // Re-apply whenever the SVG content changes or the view mode swaps.
  watch(
    () => [deps.plotSvg(), deps.originalSvg(), deps.viewMode.value],
    () => {
      // The v-html commit happens during the same flush; defer to the next
      // microtask so the DOM is in place when we walk it.
      void Promise.resolve().then(() => {
        applyOpacityOverlay()
        applyStrokeFloor()
      })
    },
  )

  // Re-apply the opacity overlay whenever any layer's opacity_percent or
  // visibility moves.
  watch(
    () =>
      job.layers
        .map(
          (l) => `${l.layer_id}:${l.opacity_percent ?? 100}:${job.isVisible(l.layer_id) ? 1 : 0}`,
        )
        .join('|'),
    () => applyOpacityOverlay(),
  )

  // Zoom / pane-size / sheet changes all move the on-screen scale, so the
  // stroke floor must be recomputed (debounced).
  let strokeFloorTimer: ReturnType<typeof setTimeout> | null = null
  watch([deps.zoom, deps.paneWidth, deps.paneHeight, deps.artworkStyle], () => {
    if (strokeFloorTimer !== null) clearTimeout(strokeFloorTimer)
    strokeFloorTimer = setTimeout(() => {
      strokeFloorTimer = null
      applyStrokeFloor()
    }, STROKE_FLOOR_DEBOUNCE_MS)
  })
  onScopeDispose(() => {
    if (strokeFloorTimer !== null) clearTimeout(strokeFloorTimer)
  })

  return { applyOpacityOverlay, applyStrokeFloor }
}
