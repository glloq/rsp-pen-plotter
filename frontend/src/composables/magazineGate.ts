// Print-launch magazine gate (operator feedback): before a print is
// sent to the machine, a modal asks the operator to load the needed
// inks into the magazine slots — with the ability to remap which slot
// carries which ink. Mirrors the ``confirmAction`` singleton pattern:
// module-level reactive state + a promise the launch site awaits, with
// the modal component (MagazineLoadModal, mounted once in App.vue)
// driving the resolution.

import { reactive } from 'vue'
import { useJobStore } from '../stores/job'

export type MagazineGateResult = 'confirmed' | 'cancelled' | 'skipped'

interface MagazineGateState {
  open: boolean
  resolve: ((value: MagazineGateResult) => void) | null
}

const state = reactive<MagazineGateState>({
  open: false,
  resolve: null,
})

export function useMagazineGateState(): MagazineGateState {
  return state
}

/**
 * Gate a print launch on the inks being loaded.
 *
 * Returns ``'skipped'`` immediately when no loading step is relevant
 * (no layers, or a single ink) — the caller then keeps its regular
 * confirmation dialog. Otherwise opens the MagazineLoadModal and
 * resolves ``'confirmed'`` (plan applied, G-code up to date, modal
 * showed its own launch button) or ``'cancelled'``.
 *
 * The modal now covers EVERY machine, not just multi-slot magazines.
 * On a single-holder machine (``pen_slot_count`` 1) the loading plan is
 * one initial pen plus one manual swap per colour change — the operator
 * is prompted to load the first ink before launch and to swap at each
 * subsequent colour. There is no firmware auto-change path: every ink
 * load / swap goes through this modal (and the mid-print pauses).
 */
export function ensureMagazineLoaded(): Promise<MagazineGateResult> {
  const job = useJobStore()
  const slotCount = job.selectedProfile?.pen_slot_count ?? 0
  const inks = new Set(
    job.layers.map((l) => (l.assigned_color_hex ?? l.source_color).toLowerCase()),
  )
  // No holder to plan against, no layers, or a single ink → nothing to
  // load or swap, so keep the caller's regular confirmation dialog.
  if (slotCount < 1 || job.layers.length === 0 || inks.size < 2) {
    return Promise.resolve('skipped')
  }
  // Settle a dangling previous gate (double-click on Play) as cancelled
  // before the new one takes over the singleton modal state.
  state.resolve?.('cancelled')
  state.resolve = null
  state.open = true
  return new Promise((resolve) => {
    state.resolve = resolve
  })
}

export function resolveMagazineGate(value: MagazineGateResult): void {
  state.open = false
  state.resolve?.(value)
  state.resolve = null
}
