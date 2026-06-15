// Expert-mode preview forwarding + cost estimate for the V2 editor.
//
// Extracted from ``EditModalV2.vue`` (Phase 4 of the editor audit). The
// expert Image / SVG / Style / Text cards mutate a singleton bitmap draft
// whose watcher fires ``/preview`` through the file manager's scheduler.
// That endpoint returns the freshly preprocessed + segmented + rendered
// SVG, which the assisted ``/rerender`` path doesn't hit — so this
// composable forwards the scheduler's SVG to the preview pane WHILE the
// operator is in expert mode, and falls back to the resolver-driven render
// otherwise. It also owns the source-image URL (for Original/Compare) and
// the per-run latency estimate that drives the loading bar.
import { computed, type ComputedRef, type Ref } from 'vue'
import { libraryFilePreviewImageUrl } from '../api/client'
import { recolorPreviewSvg } from '../lib/previewRecolor'
import type { PreviewSnap } from './useEditorInkSwatches'
import { useAlgorithmsStore } from '../stores/algorithms'
import { useBitmapDraft } from './useBitmapDraft'
import { useEditState } from './useEditState'
import { useJobStore } from '../stores/job'
import { usePreviewCostEstimator } from './usePreviewCostEstimator'
import { useUiModeStore } from '../stores/uiMode'

// The slice of ``useFileManager`` the expert preview reads. Structural so
// the modal passes its owner instance verbatim.
export interface ExpertPreviewFileManager {
  previewSvg: Ref<string>
  previewLoading: Ref<boolean>
  selectedFilePlacementId: Ref<string | null>
}

export interface EditorExpertPreviewDeps {
  fileManager: ExpertPreviewFileManager
  /** Centroid→pool snap from ``useEditorInkSwatches`` (recolours the raw
   *  /preview SVG so it matches the chips). */
  previewInkSnap: Ref<PreviewSnap | null> | ComputedRef<PreviewSnap | null>
  /** The resolver-driven adapted render (assisted pipeline). */
  renderedSvg: Ref<string | null>
  /** Whether the assisted pipeline's render is in flight. */
  pipelineLoading: Ref<boolean>
}

export function useEditorExpertPreview(deps: EditorExpertPreviewDeps) {
  const uiMode = useUiModeStore()
  const job = useJobStore()
  const bitmapDraft = useBitmapDraft()
  const editState = useEditState()
  const costEstimator = usePreviewCostEstimator()
  const algorithmsCatalog = useAlgorithmsStore()

  // Forward the expert scheduler's SVG only in expert mode AND when it has
  // produced a result for THIS placement. The previewer singleton outlives
  // the modal, so its ``previewSvg`` can still hold the previous placement's
  // render in the window between switching files and the new /preview
  // returning — gate on the placement id the in-memory File was loaded for
  // (filename equality is too weak). Otherwise fall back to the
  // resolver-driven ``renderedSvg`` so the assisted wizard is untouched.
  const expertPreviewSvg = computed<string | null>(() => {
    if (!uiMode.isExpert) return null
    const svg = deps.fileManager.previewSvg.value
    if (!svg || svg.length === 0) return null
    const fileForPlacement = deps.fileManager.selectedFilePlacementId.value
    const activePlacement = job.selectedPlacementId
    if (!fileForPlacement || !activePlacement) return null
    if (fileForPlacement !== activePlacement) return null
    // Recolour the raw centroid render to the pool inks the chips list (and
    // the print will use), so the operator doesn't see the photo's own
    // colours in the preview while only a handful of pens are listed below.
    const snap = deps.previewInkSnap.value
    return snap ? recolorPreviewSvg(svg, snap.map) : svg
  })
  const expertPreviewLoading = computed<boolean>(() => {
    if (!uiMode.isExpert) return false
    return Boolean(deps.fileManager.previewLoading.value)
  })
  const effectivePreviewSvg = computed<string | null>(
    () => expertPreviewSvg.value ?? deps.renderedSvg.value,
  )
  const effectivePreviewLoading = computed<boolean>(
    () => expertPreviewLoading.value || deps.pipelineLoading.value,
  )

  // Expected latency of the in-flight /preview for the active algorithm ×
  // quality tier — the EMA the cost estimator maintains from past
  // ``elapsed_ms`` observations. Drives the determinate progress bar.
  const previewEstimateMs = computed<number>(() => {
    // Touch the samples ref so a fresh EMA observation re-evaluates the
    // estimate for the *next* run.
    void costEstimator.samples.value
    const algo = bitmapDraft.bitmap.value.algorithm
    // Manifest complexity seeds the estimate before the first real
    // observation — a 'high' algorithm (string_art, reaction_diffusion)
    // starts near its real cost instead of the generic medium seed.
    const complexity = algorithmsCatalog.byId.get(algo)?.complexity as
      | 'low'
      | 'medium'
      | 'high'
      | undefined
    return costEstimator.estimateMs(algo, editState.previewQuality.value, complexity)
  })

  // Source image URL — fed to the pane's Original / Compare modes so the
  // operator sees the actual uploaded photo vs. the converted result.
  // ``libraryFilePreviewImageUrl`` works for every supported source type;
  // null when the placement isn't backed by a library file yet.
  const sourceImageUrl = computed<string | null>(() => {
    const id = job.selectedPlacement?.library_file_id
    if (!id) return null
    const page = Number(job.selectedPlacement?.upload_metadata?.page ?? 0)
    return libraryFilePreviewImageUrl(id, Number.isFinite(page) ? page : 0)
  })

  return {
    expertPreviewSvg,
    expertPreviewLoading,
    effectivePreviewSvg,
    effectivePreviewLoading,
    previewEstimateMs,
    sourceImageUrl,
  }
}
