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
import { assignPoolHexes } from '../lib/nearestColor'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useBitmapDraft } from './useBitmapDraft'
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
}

export interface PreviewSnap {
  /** centroid hex (lowercased) → the pool ink it draws with. */
  map: Map<string, string>
  /** Per-cluster rows in document order, for the chip strip. */
  rows: { centroid: string; ink: string; isFallback: boolean }[]
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
  const bitmapDraft = useBitmapDraft()

  const inventoryNameByHex = computed<Map<string, string>>(() => {
    const map = new Map<string, string>()
    for (const entry of availableColors.colors) {
      if (entry.name && entry.name.trim()) {
        map.set(entry.hex.toLowerCase(), entry.name)
      }
    }
    return map
  })

  // Live-preview centroid → pool-ink mapping (expert mode only).
  //
  // The /preview SVG renders each cluster in its raw segmentation CENTROID
  // (the expert draft doesn't ship ``ink_pool``), but after Apply the job
  // store re-snaps every layer onto the active pool with the same
  // greedy-unique ΔE matching. The chips already show those snapped inks;
  // this exposes the per-centroid snap once so BOTH the chips and the
  // preview recolor read from it. Without sharing the map, the preview kept
  // showing the photo's own colours while the chip strip listed only the
  // few pens that will actually draw — "la preview a plus de couleurs que
  // celles listées". ``null`` outside expert mode / before a live palette
  // exists, so the assisted pipeline (which already renders snapped inks via
  // /rerender + inkColorsFor) is untouched.
  const previewInkSnap = computed<PreviewSnap | null>(() => {
    const livePalette = deps.fileManager.previewResult?.value?.palette ?? null
    if (!uiMode.isExpert || !livePalette || livePalette.length === 0) return null
    // "Fidèle à l'image": picking an image-clustering method (kmeans /
    // kmeans_lab) turns ``paletteFollowsPens`` off — the operator asked to
    // render the photo's OWN colours, not the pen rack. Snapping those
    // centroids onto the owned pool here would silently override that choice
    // with the few closest pens (the "mauvaises couleurs comme avant"
    // report: both palette modes looked identical because both snapped).
    // Show the centroids verbatim instead — identity map, so the preview SVG
    // is left untouched and the chips list the image's real colours. Only
    // snap when the operator opted to follow the pens.
    if (!bitmapDraft.paletteFollowsPens.value) {
      const rows = livePalette.map((entry) => ({
        centroid: entry.color,
        ink: entry.color,
        isFallback: false,
      }))
      // Empty map → ``recolorPreviewSvg`` is a no-op (keeps image colours).
      return { map: new Map<string, string>(), rows }
    }
    const pool = deps.effectivePool.value
    const snapped = assignPoolHexes(
      livePalette.map((entry) => ({ sourceHex: entry.color })),
      pool,
    )
    const map = new Map<string, string>()
    const rows = livePalette.map((entry, idx) => {
      const ink = snapped[idx] ?? entry.color
      // Map even fallback clusters (ink === centroid) so the recolor pass
      // is a no-op for them rather than leaving a gap.
      map.set(entry.color.toLowerCase(), ink)
      return { centroid: entry.color, ink, isFallback: snapped[idx] === null }
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
        // Synthesise a stable layerId so the v-for keys stay stable across
        // renders. The /preview palette doesn't carry layer ids; we tag them
        // by index in cluster order.
        return {
          layerId: `preview-${idx}-${hex.replace('#', '')}`,
          hex,
          name,
          displayName: name,
          displayHex: namedMatch ? hex : '',
          isFallback: row.isFallback,
        }
      })
    }
    const layers = job.selectedPlacement?.layers ?? []
    const ordered = [...layers].sort((a, b) => a.draw_order - b.draw_order)
    return ordered.map((layer) => {
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
      }
    })
  })

  return { previewInkSnap, inkSwatches, inventoryNameByHex }
}
