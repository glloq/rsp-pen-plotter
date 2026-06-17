import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { GcodeFileSummary } from '../api/client'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useGcodeFilesStore } from '../stores/gcodeFiles'
import { useJobStore } from '../stores/job'

// Save the current generated program into the G-code library.
//
// Shared by the Simulator-tab "Save G-code" action (and any other
// surface that needs to persist the current job). Saving never starts a
// print — it only stores the program for later. It also advances the ink
// odometer: the saved file no longer carries per-colour lengths, so this
// is the one point where the consumed length still matches the current
// job's data.
export function useSaveCurrentGcode() {
  const job = useJobStore()
  const files = useGcodeFilesStore()
  const availableColors = useAvailableColorsStore()
  const { saving } = storeToRefs(files)

  const canSave = computed(() => Boolean(job.gcode))

  function logOdometerForCurrentJob(): void {
    for (const [hex, mm] of Object.entries(job.lengthMmByColor)) {
      void availableColors.addToOdometer(hex, mm)
    }
  }

  async function saveCurrent(): Promise<GcodeFileSummary | null> {
    if (!job.gcode) return null
    const name = job.job?.source_file ?? 'gcode'
    const created = await files.save(name, job.selectedProfileName, job.gcode)
    if (created) logOdometerForCurrentJob()
    return created
  }

  return { canSave, saving, saveCurrent }
}
