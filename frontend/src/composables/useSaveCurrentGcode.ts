import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import type { GcodeFileSummary } from '../api/client'
import { useGcodeFilesStore } from '../stores/gcodeFiles'
import { useJobStore } from '../stores/job'

// Save the current generated program into the G-code library.
//
// Saving only stores the program for later — it never starts a print and
// never touches the ink odometer. Ink is accounted for when a plot is
// actually launched on the machine (see ``useInkOdometer``), not when a
// file is saved, so the counters reflect ink put on paper.
export function useSaveCurrentGcode() {
  const job = useJobStore()
  const files = useGcodeFilesStore()
  const { saving } = storeToRefs(files)

  const canSave = computed(() => Boolean(job.gcode))

  async function saveCurrent(): Promise<GcodeFileSummary | null> {
    if (!job.gcode) return null
    const name = job.job?.source_file ?? 'gcode'
    return files.save(name, job.selectedProfileName, job.gcode)
  }

  return { canSave, saving, saveCurrent }
}
