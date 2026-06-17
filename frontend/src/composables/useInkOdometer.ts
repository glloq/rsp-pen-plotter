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

  // Advance each ink's odometer by the given per-colour lengths (mm,
  // keyed by canonical hex). Used both for the current job and for a
  // saved file's stored lengths on a library re-print.
  function commit(lengthMmByColor: Record<string, number>): void {
    for (const [hex, mm] of Object.entries(lengthMmByColor)) {
      void availableColors.addToOdometer(hex, mm)
    }
  }

  // Convenience: commit the current job's per-colour lengths.
  function commitCurrentJob(): void {
    commit(job.lengthMmByColor)
  }

  return { commit, commitCurrentJob }
}
