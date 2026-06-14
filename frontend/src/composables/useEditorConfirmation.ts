// Confirmation + expert-draft commit for the V2 editor modal.
//
// Extracted from ``EditModalV2.vue`` (Phase 2 of the editor audit). Owns
// the race-safe "Generate" path: in expert mode an operator who tweaked
// the image / SVG / style tabs expects those changes to land in the
// final G-code, so ``confirm`` commits the dirty draft through
// ``uploadSelected`` and AWAITS it before emitting — the parent never
// generates from the pre-apply SVG. A failed upload aborts confirm and
// surfaces ``applyError`` instead of generating from un-applied work.
import { ref, type ComputedRef, type Ref } from 'vue'
import type { PolicyDecision, PolicyPass } from '../domain/policy/schemas'
import { errorMessage } from '../lib/errorMessage'

// The slice of ``useFileManager`` the commit needs — kept structural so
// callers pass the modal's owner instance verbatim.
export interface ConfirmationFileManager {
  uploadSelected: () => Promise<void>
}

export interface EditorConfirmationDeps {
  isExpert: Ref<boolean> | ComputedRef<boolean>
  hasPlacement: Ref<boolean> | ComputedRef<boolean>
  decision: Ref<PolicyDecision | null>
  /** Whether the expert (V1) draft has uncommitted mutations. */
  isDirty: Ref<boolean> | ComputedRef<boolean>
  customStylesActive: Ref<boolean> | ComputedRef<boolean>
  customPasses: Ref<PolicyPass[]> | ComputedRef<PolicyPass[]>
  fileManager: ConfirmationFileManager
  /** Emit the final decision to the parent (the modal's ``confirm`` event). */
  onConfirm: (decision: PolicyDecision) => void
}

export function useEditorConfirmation(deps: EditorConfirmationDeps) {
  // True while an expert draft is being committed and ``confirm`` is
  // waiting on it. Locks the footer actions (Apply / Generate) so the
  // operator can't double-fire mid-upload.
  const applying = ref(false)
  // Reason the last expert apply failed, surfaced in the footer. Cleared
  // when a fresh apply starts. Non-null means ``confirm`` aborted instead
  // of generating from un-applied changes.
  const applyError = ref<string | null>(null)

  // Commit the V1 draft mutations back to the placement by re-running
  // /upload with the freshly built options bundle (the V1 "Apply" path).
  // No-op when nothing is dirty. Returns whether the placement is safe to
  // generate from: ``true`` when there was nothing to apply or the upload
  // landed, ``false`` when it threw (``applyError`` then carries why).
  async function applyExpertDraft(): Promise<boolean> {
    if (!deps.isDirty.value) return true
    applying.value = true
    applyError.value = null
    try {
      await deps.fileManager.uploadSelected()
      return true
    } catch (err) {
      applyError.value = errorMessage(err)
      return false
    } finally {
      applying.value = false
    }
  }

  async function confirm(): Promise<void> {
    if (!deps.hasPlacement.value || !deps.decision.value || applying.value) return
    if (deps.isExpert.value) {
      const ok = await applyExpertDraft()
      if (!ok) return
      // ``applyExpertDraft`` may have re-uploaded and rehydrated the
      // placement; re-check before emitting against possibly-cleared state.
      if (!deps.hasPlacement.value || !deps.decision.value) return
    }
    if (deps.customStylesActive.value) {
      // Override the resolver's algorithm pick with the operator's manual
      // stack while keeping every other field the resolver decided
      // (segmentation method, quality tier, fallback chain, …). First pass
      // mirrors ``default_algorithm`` / ``default_options`` per the
      // PolicyDecision contract (see schemas.ts ``default_passes`` doc).
      const passes = deps.customPasses.value
      const first = passes[0]!
      deps.onConfirm({
        ...deps.decision.value,
        default_algorithm: first.algorithm,
        default_options: first.algorithm_options,
        default_passes: passes,
      })
      return
    }
    deps.onConfirm(deps.decision.value)
  }

  return { applying, applyError, applyExpertDraft, confirm }
}
