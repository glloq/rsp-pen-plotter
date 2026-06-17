import { confirmAction } from './confirm'
import { ensureMagazineLoaded } from './magazineGate'
import { useInkOdometer } from './useInkOdometer'
import { i18n } from '../i18n'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

// Launch the current job on the plotter — the one shared path behind both
// the header transport "Send job" and the Simulation-tab "Start print".
//
// Centralising it here (rather than duplicating the gate → confirm → run
// sequence in each button) keeps the ink-odometer commit in a single
// place: every real launch of the current job accounts for ink exactly
// once, and a future launch surface inherits the same behaviour for free.
//
// ``launching`` is module-level on purpose: the two buttons drive the
// SAME current job, so a near-simultaneous double-fire (double-click, or
// header + simulator) must not send twice / double-count the odometer.
let launching = false

export function useLaunchCurrentJob() {
  const job = useJobStore()
  const plotter = usePlotterStore()
  const { commitCurrentJob } = useInkOdometer()
  const t = i18n.global.t

  async function launch(): Promise<void> {
    if (launching || !job.gcode || !plotter.status.connected) return
    launching = true
    try {
      // Magazine gate first (multi-pen multicolour jobs): the modal asks
      // to load the planned inks and carries its own launch button; the
      // generic confirm only runs when the gate was skipped.
      const gate = await ensureMagazineLoaded()
      if (gate === 'cancelled') return
      if (gate === 'skipped') {
        const confirmed = await confirmAction({
          title: t('confirm.sendJobTitle'),
          message: t('confirm.sendJobMsg'),
          confirmLabel: t('plotter.sendJob'),
          cancelLabel: t('confirm.cancel'),
        })
        if (!confirmed) return
      }
      // Re-read the G-code: confirming the gate may have regenerated it.
      if (!job.gcode) return
      await plotter.run(job.gcode)
      // Advance the ink odometer only on a real, successful launch
      // (``run`` swallows failures into ``plotter.error``); never on save.
      if (!plotter.error) commitCurrentJob()
    } finally {
      launching = false
    }
  }

  return { launch }
}
