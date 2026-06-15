// Ink-swatch strip + live-preview cluster→ink mapping for the V2 editor.
//
// Owns the chips under the preview and the per-cluster ink each one draws
// with. The strip must stay fully functional AT ALL TIMES — hide a layer and
// re-assign its ink — even on a fresh, never-committed image, so the expert
// live /preview clusters carry their OWN editor-scoped state (colour override +
// visibility) keyed by a stable per-cluster id, instead of depending on
// committed ``job.layers`` (which may be empty or out of sync after a
// colour-count change). Assisted mode keeps reading the committed layers, which
// already carry the backend's ink assignment + geometry.
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { ColorAssignment, LayerInfo } from '../api/client'
import { assignPoolHexes, nearestPoolHex } from '../lib/nearestColor'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { useUiModeStore } from '../stores/uiMode'

export interface InkSwatch {
  layerId: string
  hex: string
  name: string
  // Human-readable label for the chip. Inventory name when known,
  // otherwise the hex itself.
  displayName: string
  // Secondary hex caption, shown next to ``displayName`` as a small
  // monospace aside. Empty when the name already *is* the hex (no
  // inventory match) to avoid duplicating the same six characters.
  displayHex: string
  isFallback: boolean
  // The layer (real committed layer, or a synthetic one standing in for a
  // live /preview cluster) the assign-colour popover drives. Always set, so
  // the popover is offered on every chip.
  layer: LayerInfo
}

export interface PreviewSnap {
  /** centroid hex (lowercased) → the ink it draws with, or ``'none'`` for a
   *  hidden cluster (``recolorPreviewSvg`` paints it invisible). */
  map: Map<string, string>
  /** Per-cluster rows in document order, for the chip strip. */
  rows: { centroid: string; ink: string; isFallback: boolean; layer: LayerInfo }[]
}

// The slice of ``useFileManager`` the swatches need — the live /preview
// palette. Kept structural so the modal passes its owner instance verbatim.
export interface InkSwatchFileManager {
  previewResult: Ref<{ palette: { color: string }[] } | null>
}

export interface EditorInkSwatchesDeps {
  fileManager: InkSwatchFileManager
  /** The pool the operator is pointing at (machine pens / inventory / union). */
  effectivePool: Ref<string[]> | ComputedRef<string[]>
}

// A live-preview cluster's chip id. The centroid hex makes it stable across
// re-previews of the SAME segmentation (so an override survives a slider
// nudge) and naturally resets when the colour count changes (new centroids →
// new ids). The ``cluster-`` prefix tells the routing helpers below to act on
// the editor-scoped state rather than the job store.
function clusterIdFor(centroid: string): string {
  return `cluster-${centroid.replace('#', '').toLowerCase()}`
}
function isClusterId(layerId: string): boolean {
  return layerId.startsWith('cluster-')
}

// Stand-in LayerInfo for a live cluster so the shared AssignedColorPicker (which
// reads source_color / assigned_color_hex / color_assignment) works unchanged.
function makeClusterLayer(
  layerId: string,
  centroid: string,
  ink: string,
  manual: boolean,
  drawOrder: number,
): LayerInfo {
  return {
    layer_id: layerId,
    source_color: centroid,
    assigned_color_hex: ink,
    color_assignment: (manual ? 'manual' : 'auto') as ColorAssignment,
    draw_order: drawOrder,
    target_pen_slot: null,
    total_length_mm: 0,
    path_count: 0,
    bbox: { x_min: 0, y_min: 0, x_max: 0, y_max: 0 },
    optimize: true,
    simplify_tolerance_mm: 0,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
  } as LayerInfo
}

export function useEditorInkSwatches(deps: EditorInkSwatchesDeps) {
  const job = useJobStore()
  const availableColors = useAvailableColorsStore()
  const uiMode = useUiModeStore()

  // Editor-scoped per-cluster state for the live preview, keyed by cluster id.
  // Reset whenever the active placement changes so one file's tweaks can't
  // bleed into another.
  const clusterColor = ref<Map<string, string>>(new Map())
  const clusterHidden = ref<Set<string>>(new Set())
  watch(
    () => job.selectedPlacementId,
    () => {
      clusterColor.value = new Map()
      clusterHidden.value = new Set()
    },
  )

  const inventoryNameByHex = computed<Map<string, string>>(() => {
    const map = new Map<string, string>()
    for (const entry of availableColors.colors) {
      if (entry.name && entry.name.trim()) {
        map.set(entry.hex.toLowerCase(), entry.name)
      }
    }
    return map
  })

  const sortedLayers = computed<LayerInfo[]>(() => {
    const layers = job.selectedPlacement?.layers ?? []
    return [...layers].sort((a, b) => a.draw_order - b.draw_order)
  })

  // Live-preview cluster → available-ink mapping (expert mode only).
  //
  // Every cluster is snapped to its perceptually-nearest available ink (CIE Lab
  // ΔE 2000, full inventory ∪ pens pool) unless the operator pinned one via the
  // assign popover; a hidden cluster maps to ``'none'`` so the shared recolour
  // pass paints it invisible. The map feeds ``recolorPreviewSvg`` so the chips,
  // the preview and the eventual print all agree.
  const previewInkSnap = computed<PreviewSnap | null>(() => {
    const livePalette = deps.fileManager.previewResult?.value?.palette ?? null
    if (!uiMode.isExpert || !livePalette || livePalette.length === 0) return null
    const autoSnapped = assignPoolHexes(
      livePalette.map((entry) => ({ sourceHex: entry.color })),
      deps.effectivePool.value,
    )
    const map = new Map<string, string>()
    const rows = livePalette.map((entry, idx) => {
      const centroid = entry.color
      const layerId = clusterIdFor(centroid)
      const override = clusterColor.value.get(layerId) ?? null
      const auto = autoSnapped[idx] ?? centroid
      const ink = override ?? auto
      const isFallback = !override && autoSnapped[idx] === null
      const hidden = clusterHidden.value.has(layerId)
      if (hidden) {
        map.set(centroid.toLowerCase(), 'none')
      } else if (ink.toLowerCase() !== centroid.toLowerCase()) {
        map.set(centroid.toLowerCase(), ink)
      }
      const layer = makeClusterLayer(layerId, centroid, ink, override !== null, idx)
      return { centroid, ink, isFallback, layer }
    })
    return { map, rows }
  })

  const inkSwatches = computed<InkSwatch[]>(() => {
    const snap = previewInkSnap.value
    if (snap) {
      return snap.rows.map((row) => {
        const hex = row.ink
        const namedMatch = inventoryNameByHex.value.get(hex.toLowerCase())
        const name = namedMatch ?? hex
        return {
          layerId: row.layer.layer_id,
          hex,
          name,
          displayName: name,
          displayHex: namedMatch ? hex : '',
          isFallback: row.isFallback,
          layer: row.layer,
        }
      })
    }
    return sortedLayers.value.map((layer) => {
      const assigned = layer.assigned_color_hex
      const hex = assigned ?? layer.source_color
      const namedMatch = inventoryNameByHex.value.get(hex.toLowerCase())
      const name = namedMatch ?? hex
      return {
        layerId: layer.layer_id,
        hex,
        name,
        displayName: name,
        displayHex: namedMatch ? hex : '',
        isFallback: !assigned,
        layer,
      }
    })
  })

  // ---- Per-chip actions (route to cluster state OR the job store) ----

  function isSwatchVisible(layerId: string): boolean {
    if (isClusterId(layerId)) return !clusterHidden.value.has(layerId)
    return job.isVisible(layerId)
  }

  function toggleSwatchVisibility(layerId: string): void {
    if (isClusterId(layerId)) {
      const next = new Set(clusterHidden.value)
      if (next.has(layerId)) next.delete(layerId)
      else next.add(layerId)
      clusterHidden.value = next
      return
    }
    job.setVisibility(layerId, !job.isVisible(layerId))
  }

  function assignSwatchColor(layerId: string, hex: string): void {
    if (isClusterId(layerId)) {
      const next = new Map(clusterColor.value)
      next.set(layerId, hex)
      clusterColor.value = next
      return
    }
    job.updateLayer(layerId, { assigned_color_hex: hex, color_assignment: 'manual' })
  }

  function resetSwatchColor(layerId: string, hex: string | null): void {
    if (isClusterId(layerId)) {
      // Drop the override → the cluster falls back to the auto ΔE snap.
      const next = new Map(clusterColor.value)
      next.delete(layerId)
      clusterColor.value = next
      return
    }
    const fallback =
      hex ??
      nearestPoolHex(
        sortedLayers.value.find((l) => l.layer_id === layerId)?.source_color ?? '',
        deps.effectivePool.value,
      )
    job.updateLayer(layerId, { assigned_color_hex: fallback, color_assignment: 'auto' })
  }

  return {
    previewInkSnap,
    inkSwatches,
    inventoryNameByHex,
    isSwatchVisible,
    toggleSwatchVisibility,
    assignSwatchColor,
    resetSwatchColor,
  }
}
