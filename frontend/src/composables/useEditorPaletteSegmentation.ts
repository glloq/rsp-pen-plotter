// Palette-driven re-segmentation for the V2 editor modal.
//
// Extracted from ``EditModalV2.vue`` (Phase 1 of the editor audit) so the
// "re-convert the placement when the resolver wants a palette split but
// the cached segmentation used a different pool" rule can be reasoned
// about and tested without mounting the whole modal.
//
// Owns two things:
//   - ``effectivePool``: the colour pool the operator is actually
//     pointing at (machine pens, the available-colours inventory, or
//     their union, per the global palette source).
//   - ``ensureSegmentationMatchesDecision``: the round-trip that
//     re-uploads the placement with ``kmeans_lab`` + ``ink_pool`` when
//     the cached conversion no longer matches that pool.
import { computed, type Ref } from 'vue'
import type { PolicyDecision } from '../domain/policy/schemas'
import { resolveEffectivePalette } from '../lib/effectivePalette'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { usePaletteSourceStore } from '../stores/paletteSource'

// The slice of ``useFileManager`` the re-segmentation needs. Kept
// structural so callers can pass the modal's owner instance verbatim.
export interface SegmentationFileManager {
  ensureSelectedFile: () => Promise<void>
  selectedFile: Ref<File | null>
  buildOptions: () => Record<string, unknown> | undefined
}

export function useEditorPaletteSegmentation(fileManager: SegmentationFileManager) {
  const job = useJobStore()
  const paletteSource = usePaletteSourceStore()
  const availableColors = useAvailableColorsStore()

  // The pool the operator is actually pointing at. Mirrors
  // ``stores/job.currentEffectivePalette`` so the segmentation below
  // lands on exactly the swatches the chips show.
  const effectivePool = computed<string[]>(() => {
    const pens = (job.selectedProfile?.pens ?? [])
      .filter((p) => p.installed && p.color)
      .map((p) => p.color)
    const available = availableColors.ordered.map((c) => c.hex)
    return resolveEffectivePalette(paletteSource.source, pens, available)
  })

  /**
   * Re-convert the placement when the resolver wants a palette-driven
   * split but the cached segmentation was built with something else (or
   * an older pool). Round-trips /upload with the placement's own source
   * bytes so the new cluster set, layers and rerender cache all match
   * the operator's pool. The conversion is perceptual clustering
   * (``kmeans_lab``, k = pool size) + the backend's ``ink_pool`` remap —
   * each cluster draws with its own distinct pool ink, which keeps
   * working on low-saturation photos where the previous ``fixed_palette``
   * nearest-colour snap starved every non-grey pen. Skipped (cheap) when
   * the persisted ``last_options`` already carry the same pool, so this
   * runs once per placement × pool, not on every preview.
   *
   * ``onUploadStart`` lets the caller flip its loading flag the moment a
   * real re-upload is committed (so the spinner only shows when work
   * actually happens, not on the cheap skip path).
   */
  async function ensureSegmentationMatchesDecision(
    decision: PolicyDecision | null,
    controller: AbortController,
    onUploadStart?: () => void,
  ): Promise<void> {
    if (!decision || decision.segmentation_method !== 'fixed_palette') return
    const placement = job.selectedPlacement
    if (!placement || !placement.source_mime.startsWith('image/')) return
    const pool = effectivePool.value.map((h) => h.toLowerCase())
    // A 0/1-colour pool can't drive a multicolour split — keep whatever
    // segmentation the upload picked (mono pipelines own that case).
    if (pool.length < 2) return
    const last = (placement.last_options ?? {}) as Record<string, unknown>
    const lastPool = (Array.isArray(last.ink_pool) ? (last.ink_pool as string[]) : []).map((h) =>
      h.toLowerCase(),
    )
    if (
      last.segmentation_method === 'kmeans_lab' &&
      lastPool.length === pool.length &&
      lastPool.every((h, i) => h === pool[i])
    ) {
      return
    }
    await fileManager.ensureSelectedFile()
    const file = fileManager.selectedFile.value
    if (!file || controller.signal.aborted) return
    onUploadStart?.()
    const built = (fileManager.buildOptions() ?? {}) as Record<string, unknown>
    // Ask for as many clusters as inks owned (+1 for the paper-white
    // background cluster k-means spends before drop_background removes it).
    // Over-asking is harmless now that the ink remap is plain nearest-match
    // with reuse: a 3-colour image against an 8-ink pool collapses its
    // extra clusters back onto the nearest inks (3 faithful colours), while
    // a genuine 6-colour image still uses all 6 inks. The backend also caps
    // k at the image's distinct colours; 16 stays the hard ceiling.
    const dropBackground = built.drop_background !== false
    const numColors = Math.min(pool.length + (dropBackground ? 1 : 0), 16)
    const options = {
      ...built,
      segmentation_method: 'kmeans_lab',
      segmentation_options: {},
      num_colors: numColors,
      ink_pool: pool,
    }
    await job.upload(file, options)
  }

  return { effectivePool, ensureSegmentationMatchesDecision }
}
