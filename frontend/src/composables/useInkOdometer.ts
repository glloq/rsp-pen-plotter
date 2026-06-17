import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'

// Ink odometer accounting.
//
// The odometer tracks how much ink (mm drawn) each colour has consumed.
// It must advance ONLY when a plot is actually launched on the machine —
// never on save — so the counters reflect ink put on paper, not programs
// sitting in the library.
//
// Call ``commitCurrentJob`` right after a successful ``plotter.run`` of
// the current job: that's the one point where the per-colour lengths
// still match exactly what's being drawn (the saved file no longer
// carries them).
export function useInkOdometer() {
  const job = useJobStore()
  const availableColors = useAvailableColorsStore()

  function commitCurrentJob(): void {
    for (const [hex, mm] of Object.entries(job.lengthMmByColor)) {
      void availableColors.addToOdometer(hex, mm)
    }
  }

  return { commitCurrentJob }
}
