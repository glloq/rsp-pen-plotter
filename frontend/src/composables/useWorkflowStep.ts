// Single source of truth for "where is the operator in the workflow?"
// (UX audit vague 2 — PrimaryWorkflowAction).
//
// The signals were always in the stores (library contents, placements,
// missing pens, generated G-code, connection, active run) but every
// surface re-derived its own subset (``canPlay``, ``canGenerate``,
// per-tab buttons). This composable centralises the derivation into an
// ordered state machine so the primary-action bar — and any future
// surface — agrees on the ONE next step.
//
// Order matters and encodes the priority of interruptions:
// a live run always wins; then the funnel walks import → place →
// style → pens → generate → connect → launch.

import { computed, type ComputedRef } from 'vue'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'

export type WorkflowStep =
  | 'running'
  | 'paused'
  | 'empty'
  | 'imported'
  | 'placed'
  | 'preflight_blocked'
  | 'configured'
  | 'ready_disconnected'
  | 'ready'

export function useWorkflowStep(): { step: ComputedRef<WorkflowStep> } {
  const job = useJobStore()
  const library = useLibraryStore()
  const plotter = usePlotterStore()
  const queue = useQueueStore()

  const step = computed<WorkflowStep>(() => {
    // A live run overrides everything: the queue's active run is the
    // canonical lifecycle; direct ``plotter.run`` sends fall back to
    // the serial status (same precedence as the header transport).
    const run = queue.active[0]
    const runState = run?.state ?? plotter.status.state
    if (runState === 'running') return 'running'
    if (runState === 'paused') return 'paused'

    if (job.visiblePlacements.length === 0) {
      return library.files.length === 0 ? 'empty' : 'imported'
    }
    // A placement without rendered layers still needs its style pass
    // (empty draft dropped on the plan, conversion not run yet).
    if (job.visiblePlacements.some((p) => !p.svg || !p.layers.length)) return 'placed'
    if (job.missingPenSlots.length > 0) return 'preflight_blocked'
    if (!job.gcode) return 'configured'
    return plotter.status.connected ? 'ready' : 'ready_disconnected'
  })

  return { step }
}
