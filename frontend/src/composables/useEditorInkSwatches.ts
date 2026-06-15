// Ink-swatch strip + live-preview centroid→pool snap for the V2 editor.
//
// Extracted from ``EditModalV2.vue`` (Phase 4 of the editor audit) so the
// "which inks will this print use, and how does the expert /preview map
// onto the owned pool" logic can be reasoned about and tested without
// mounting the modal.
//
// Owns two reactive outputs:
//   - ``previewInkSnap``: in EXPERT mode, the per-cluster mapping from the
//     /preview's raw segmentation centroids to the pool ink each cluster
//     will actually draw with (or an identity map when the operator asked
//     to stay faithful to the image's own colours). Shared with the expert
//     preview recolour so the chips and the preview SVG always agree.
//   - ``inkSwatches``: the chip strip itself — the live /preview clusters
//     in expert mode, else the placement's committed layers in draw order.
import { computed, type ComputedRef, type Ref } from 'vue'
import type { LayerInfo } from '../api/client'
import { assignPoolHexes } from '../lib/nearestColor'
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
  // The real placement layer this chip drives — the eye toggle and the
  // assign-colour popover act on it. ``null`` only when a live /preview
  // cluster has no matching committed layer yet (segmentation changed but
  // not re-applied), in which case those per-layer controls are disabled.
  layer: LayerInfo | null
}

export interface PreviewSnap {
  /** centroid hex (lowercased) → the ink it draws with (manual override,
   *  pool snap or its own colour when faithful to the image). */
  map: Map<string, string>
  /** Per-cluster rows in document order, for the chip strip. */
  rows: { centroid: string; ink: string; isFallback: boolean; layer: LayerInfo | null }[]
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

export function useEditorInkSwatches(deps: EditorInkSwatchesDeps) {
  const job = useJobStore()
  const availableColors = useAvailableColorsStore()
  const uiMode = useUiModeStore()

  const inventoryNameByHex = computed<Map<string, string>>(() => {
    const map = new Map<string, string>()
    for (const entry of availableColors.colors) {
      if (entry.name && entry.name.trim()) {
        map.set(entry.hex.toLowerCase(), entry.name)
      }
    }
    return map
  })

  // The committed placement's layers in DRAW order — the same order the
  // /preview palette and the SVG groups come in, so a live cluster maps to
  // its real layer by index. This is what gives the expert-mode chips a
  // real ``layer_id`` (eye toggle + colour assignment), and what lets a
  // manual ink override recolour the live preview.
  const sortedLayers = computed<LayerInfo[]>(() => {
    const layers = job.selectedPlacement?.layers ?? []
    return [...layers].sort((a, b) => a.draw_order - b.draw_order)
  })

  // Live-preview centroid → available-ink mapping (expert mode only).
  //
  // The /preview SVG renders each cluster in its raw segmentation CENTROID
  // (the expert draft ships no ``ink_pool``). A pen plotter can only draw
  // with the inks the operator owns, so EVERY cluster is snapped here to its
  // perceptually-nearest available ink (CIE Lab ΔE 2000, full inventory ∪ pens
  // pool) — the chips and the recoloured preview therefore always show real
  // available colours, never the image's own centroids. The map is shared with
  // the expert preview recolour so the chips and the SVG agree on the ink drawn.
  const previewInkSnap = computed<PreviewSnap | null>(() => {
    const livePalette = deps.fileManager.previewResult?.value?.palette ?? null
    if (!uiMode.isExpert || !livePalette || livePalette.length === 0) return null
    const pool = deps.effectivePool.value
    // Always snap every cluster onto the owned pool. Reuse is allowed (two
    // clusters nearest the same ink both draw it) so a pool that doesn't span
    // the image collapses onto the closest inks instead of scattering greens
    // onto blue/grey. ``null`` per item only when the pool is empty.
    const autoSnapped = assignPoolHexes(
      livePalette.map((entry) => ({ sourceHex: entry.color })),
      pool,
    )
    // Manual overrides + the per-chip layer handle come from the committed
    // layers ONLY while the live segmentation still matches them (same cluster
    // count ⇒ same clusters, in draw order). The moment the operator changes
    // the colour count in the SVG tab the committed layers are stale, so we map
    // purely from the live centroids — index-mapping onto stale layers is
    // exactly what assigned "blue for green / grey for green".
    const layers = sortedLayers.value
    const aligned = layers.length === livePalette.length ? layers : null
    const map = new Map<string, string>()
    const rows = livePalette.map((entry, idx) => {
      const centroid = entry.color
      const layer = aligned ? (aligned[idx] ?? null) : null
      const manual =
        layer && layer.color_assignment === 'manual' && layer.assigned_color_hex
          ? layer.assigned_color_hex
          : null
      const auto = autoSnapped[idx] ?? centroid
      const ink = manual ?? auto
      // Fallback = the pool was empty so no owned ink could be picked (the chip
      // surfaces a "load this ink" CTA). A successful snap is never a fallback.
      const isFallback = !manual && autoSnapped[idx] === null
      // Record the remap so ``recolorPreviewSvg`` paints the cluster in its
      // assigned ink. An ink equal to the centroid (pool already held that
      // exact colour) needs no rewrite.
      if (ink.toLowerCase() !== centroid.toLowerCase()) {
        map.set(centroid.toLowerCase(), ink)
      }
      return { centroid, ink, isFallback, layer }
    })
    return { map, rows }
  })

  const inkSwatches = computed<InkSwatch[]>(() => {
    // Prefer the LIVE /preview palette when the V1 cards have just produced
    // one (expert mode tweaks): it reflects what the operator is actually
    // about to commit on Apply. Falls back to the placement's committed
    // layers so assisted mode + fresh sessions keep their chip strip.
    // Expert mode: the chips mirror the live /preview clusters, snapped onto
    // the active pool by ``previewInkSnap`` (the same map that recolours the
    // preview SVG, so chips and preview agree on the inks drawn).
    const snap = previewInkSnap.value
    if (snap) {
      return snap.rows.map((row, idx) => {
        const hex = row.ink
        const namedMatch = inventoryNameByHex.value.get(hex.toLowerCase())
        const name = namedMatch ?? hex
        // Drive the chip from its real layer so the eye toggle + assign
        // popover act on the placement. Only when a live cluster has no
        // matching committed layer (segmentation changed but not applied)
        // do we fall back to a synthesised, control-less id.
        return {
          layerId: row.layer?.layer_id ?? `preview-${idx}-${hex.replace('#', '')}`,
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

  return { previewInkSnap, inkSwatches, inventoryNameByHex }
}
