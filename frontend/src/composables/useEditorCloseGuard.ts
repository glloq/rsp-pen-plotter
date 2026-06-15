// Single close gate for the V2 editor modal.
//
// Every way out of the modal — the header ✕, the footer "Annuler", the
// backdrop click and the Escape key — funnels through ``requestClose`` so
// the two close-time hazards from the audit (P1 §3 / §4) are handled in
// exactly one place instead of four:
//
//   - While an expert draft is being committed (``applying``), closing is
//     BLOCKED. The upload is in flight and ``confirm`` may still emit; a
//     close here would desync the visual state from the real generate
//     action. The footer already disables Apply / Generate during this
//     window, so the operator only has to wait for the commit to land.
//   - With unsaved expert changes (``isDirty``), closing asks for explicit
//     confirmation so brightness / segmentation / style / typography tweaks
//     aren't silently dropped.
import type { ComputedRef, Ref } from 'vue'

export interface EditorCloseGuardDeps {
  /** An expert draft is mid-commit — block the close until it settles. */
  applying: Ref<boolean> | ComputedRef<boolean>
  /** The expert draft has uncommitted mutations — confirm before closing. */
  isDirty: Ref<boolean> | ComputedRef<boolean>
  /** Ask the operator to confirm discarding unsaved changes. Returns true
   *  to proceed. Injected (defaults to ``window.confirm`` at the call site)
   *  so the guard stays testable without a real dialog. */
  confirmDiscard: () => boolean
  /** Actually close the modal (the host's ``emit('cancel')``). */
  onClose: () => void
}

export function useEditorCloseGuard(deps: EditorCloseGuardDeps) {
  function requestClose(): void {
    if (deps.applying.value) return
    if (deps.isDirty.value && !deps.confirmDiscard()) return
    deps.onClose()
  }
  return { requestClose }
}
