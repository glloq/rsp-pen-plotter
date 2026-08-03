import { computed, watch } from 'vue'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore, type CameraConfig } from '../stores/ui'

// Plotter run-states that mean "a print is on the bed". The device status
// reflects both direct sends and queue-driven jobs, so watching it covers
// every launch path.
const PRINT_ACTIVE_STATES = new Set(['running', 'paused', 'waiting'])

// Resolve which camera URL to record from: the chosen slot if it's a
// configured camera, otherwise the first configured one (empty if none).
export function resolveCameraUrl(cameras: readonly CameraConfig[], slot: number): string {
  const chosen = cameras[slot]
  if (chosen?.enabled && chosen.url.trim()) return chosen.url.trim()
  const first = cameras.find((c) => c.enabled && c.url.trim())
  return first ? first.url.trim() : ''
}

// Auto-record a timelapse for the duration of a print when enabled in the
// timelapse settings. Only auto-stops a recording it auto-started, so a
// manual timelapse is never cut short. Call once during app setup.
export function useTimelapseAutoCapture(): void {
  const plotter = usePlotterStore()
  const timelapse = useTimelapseStore()
  const ui = useUiStore()
  const job = useJobStore()

  // Tracks whether the in-flight recording was started by this hook.
  let autoActive = false
  const printActive = computed(() => PRINT_ACTIVE_STATES.has(plotter.status.state))

  watch(printActive, async (active, was) => {
    if (active && !was) {
      // A print started — begin a timelapse if enabled and idle.
      if (!timelapse.autoEnabled || timelapse.status.recording) return
      const url = resolveCameraUrl(ui.cameras, timelapse.cameraSlot)
      if (!url) return
      const label = job.job?.source_file?.trim() || 'print'
      autoActive = await timelapse.start(url, timelapse.intervalSeconds, timelapse.fps, label)
      // A very short print (or a slow backend) can finish while ``start`` is
      // still in flight — the stop branch below would have run with
      // ``autoActive`` still false and left the recording running over an idle
      // bed. Re-check once ``start`` resolves and stop what we just started.
      if (autoActive && !printActive.value && timelapse.status.recording) {
        autoActive = false
        await timelapse.stop()
      }
    } else if (!active && was) {
      // The print ended — stop only what we auto-started. If ``start`` is still
      // in flight, its post-await re-check above stops the recording instead.
      if (autoActive && timelapse.status.recording) await timelapse.stop()
      autoActive = false
    }
  })
}
