import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type CanvasTab = 'sheet' | 'simulator' | 'files' | 'plotter'
// Top-level sections of the centred Settings modal. The former
// developer/diagnostics tabs (audit, slo, manifests) are no longer
// first-class tabs — they're collapsed under the single ``advanced``
// section so the panel reads as operator settings, not observability.
export type SettingsTab = 'system' | 'cameras' | 'history' | 'advanced'
export type PlotterTab = 'connection' | 'profile' | 'colors' | 'macros' | 'queue'

export interface PreviewSheet {
  width_mm: number
  height_mm: number
  // Top-left offset of the sheet zone on the workspace (mm). Optional so
  // callers that only care about the format can omit it (defaults to 0,0,
  // i.e. the workspace top-left).
  x_mm?: number
  y_mm?: number
}

export type UpdatePhase = 'idle' | 'running' | 'success' | 'noop' | 'error'

// State machine for the G-code generation progress modal. Mirrors the
// shape of UpdateModalState but is driven by the job store's generate()
// flow (optimize → preflight → generate). ``cancelled`` is a terminal
// phase distinct from ``error`` so the modal can show a neutral message.
export type GcodeJobPhase = 'idle' | 'running' | 'success' | 'cancelled' | 'error'

export type GcodeJobStep = 'optimize' | 'preflight' | 'generate'

export interface GcodeJobState {
  phase: GcodeJobPhase
  step: GcodeJobStep | null
  message: string
  error: string | null
  startedAt: number | null
  // Seed estimate (seconds) for the whole optimize → preflight → generate
  // pipeline, learned from past runs (``durationEstimator``). Drives the
  // modal's determinate bar + remaining-time readout. Null on the very
  // first run (no history) — the modal falls back to an indeterminate
  // spinner + elapsed counter.
  etaSeconds: number | null
}

export interface UpdateModalState {
  phase: UpdatePhase
  // Free-form status line shown under the spinner (e.g. "Pulling latest…").
  // Localised at the call site so the store stays string-agnostic.
  message: string
  // Populated when ``phase === 'error'`` so the modal can render the cause.
  error: string | null
  // Wall-clock start, used to render an elapsed timer.
  startedAt: number | null
  // Forced-update flag echoed back from the API — surfaces the "local
  // changes were discarded" banner in the modal.
  forced: boolean
  // Set on a successful upgrade so the modal can show the Ctrl+Shift+R
  // reminder and a Reload button. Distinct from ``phase === 'success'``
  // because a no-op still ends in success but doesn't need the reminder.
  newCommitApplied: boolean
  // Seed estimate (seconds) for the update, learned from past updates
  // (``durationEstimator``). Drives a determinate bar + remaining-time.
  // Null on the first update (no history) → indeterminate spinner. Updates
  // are genuinely unpredictable (npm/build/network), so past the estimate
  // the modal shows a "taking longer than usual" hint, not a fake countdown.
  etaSeconds: number | null
}

const UPDATE_NOTIFY_KEY = 'omniplot.updateNotifications'

function loadUpdateNotifications(): boolean {
  try {
    const raw = localStorage.getItem(UPDATE_NOTIFY_KEY)
    // Default ON: first-time users see the notification until they opt out.
    if (raw === null) return true
    return raw === '1'
  } catch {
    return true
  }
}

// How the plan (sheet) tab paints each placement:
//   - 'image' : always the original raster source (cheapest to paint,
//               heavy vector styles never touch the canvas)
//   - 'svg'   : always the chosen-style plotter SVG (a true WYSIWYG of
//               what will be drawn), raster only as a pre-conversion
//               fallback
//   - 'auto'  : prefer the style SVG, but fall back to the raster when
//               the SVG is dense enough to risk laggy pan/zoom — the
//               "best of both" default
export type PlanPreviewMode = 'image' | 'svg' | 'auto'

const PLAN_PREVIEW_KEY = 'omniplot.planPreviewMode'

function loadPlanPreviewMode(): PlanPreviewMode {
  try {
    const raw = localStorage.getItem(PLAN_PREVIEW_KEY)
    if (raw === 'image' || raw === 'svg' || raw === 'auto') return raw
    // Default to the adaptive mode: WYSIWYG when it's cheap, raster when
    // the vector is too heavy to scroll smoothly.
    return 'auto'
  } catch {
    return 'auto'
  }
}

// Optional workshop cameras (up to two — typically one). Each is an
// MJPEG/HTTP stream URL, which is hardware-agnostic: a USB webcam
// (mjpg-streamer / ustreamer), a Raspberry Pi CSI camera (ustreamer /
// libcamera) or an IP camera all expose one. When enabled with a URL the
// Plotter tab shows the feed above the manual cockpit. Stored client-side
// (like the other System-settings preferences).
export interface CameraConfig {
  enabled: boolean
  url: string
  // Operator-facing name (falls back to "Camera N" when blank).
  label: string
}

// Fixed two slots so the config UI and the persisted shape stay stable;
// the second is opt-in (disabled + blank by default).
export const MAX_CAMERAS = 2

const CAMERAS_KEY = 'omniplot.cameras'
// Legacy single-camera keys, migrated into slot 0 on first load.
const CAMERA_ENABLED_KEY = 'omniplot.cameraEnabled'
const CAMERA_URL_KEY = 'omniplot.cameraUrl'

function blankCamera(): CameraConfig {
  return { enabled: false, url: '', label: '' }
}

function normalizeCamera(raw: unknown): CameraConfig {
  const o = (raw ?? {}) as Record<string, unknown>
  return {
    enabled: o.enabled === true,
    url: typeof o.url === 'string' ? o.url : '',
    label: typeof o.label === 'string' ? o.label : '',
  }
}

function loadCameras(): CameraConfig[] {
  const padded = (list: CameraConfig[]): CameraConfig[] => {
    const out = list.slice(0, MAX_CAMERAS)
    while (out.length < MAX_CAMERAS) out.push(blankCamera())
    return out
  }
  try {
    const raw = localStorage.getItem(CAMERAS_KEY)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (Array.isArray(parsed)) return padded(parsed.map(normalizeCamera))
    }
    // Migrate the pre-2-camera single config into slot 0.
    const legacyUrl = localStorage.getItem(CAMERA_URL_KEY)
    const legacyEnabled = localStorage.getItem(CAMERA_ENABLED_KEY) === '1'
    if (legacyUrl !== null || legacyEnabled) {
      return padded([{ enabled: legacyEnabled, url: legacyUrl ?? '', label: '' }])
    }
  } catch {
    // localStorage unavailable / malformed JSON — fall through to default.
  }
  return padded([])
}

export const useUiStore = defineStore('ui', () => {
  const canvasTab = ref<CanvasTab>('sheet')
  const settingsOpen = ref(false)
  const settingsTab = ref<SettingsTab>('system')
  // Independent plotter-settings modal (connection, profile, colors,
  // macros, queue). The main-page ``plotter`` canvas tab now hosts only
  // the manual control; everything else lives in this modal.
  const plotterSettingsOpen = ref(false)
  const plotterTab = ref<PlotterTab>('connection')
  // Monotonic counter bumped by the empty-plan CTA ("pick from the
  // library"): FilesPane watches it and flashes a highlight ring so the
  // operator's eye lands on the library pane. A counter (not a boolean)
  // so repeated clicks re-trigger the pulse.
  const filesPanePulse = ref(0)
  function pulseFilesPane(): void {
    filesPanePulse.value += 1
  }
  const editModalOpen = ref(false)
  // Display-only sheet overlay shown on the workspace plan, positioned at
  // the top-left. Set when the user picks a sheet format in LayoutSection.
  const previewSheet = ref<PreviewSheet | null>(null)

  const updateState = ref<UpdateModalState>({
    phase: 'idle',
    message: '',
    error: null,
    startedAt: null,
    forced: false,
    newCommitApplied: false,
    etaSeconds: null,
  })

  // G-code generation progress modal. ``cancelFn`` is the AbortController
  // hook installed by job.generate(); the modal's Cancel button calls it
  // to abort the in-flight POST. Lives on the store (rather than as a
  // closure on the modal) so any caller — keyboard escape handler,
  // toast, navigation guard — can trigger cancellation uniformly.
  const gcodeJobState = ref<GcodeJobState>({
    phase: 'idle',
    step: null,
    message: '',
    error: null,
    startedAt: null,
    etaSeconds: null,
  })
  const gcodeJobCancel = ref<(() => void) | null>(null)

  function startGcodeJob(
    step: GcodeJobStep,
    message: string,
    cancel: () => void,
    etaSeconds: number | null = null,
  ): void {
    gcodeJobCancel.value = cancel
    gcodeJobState.value = {
      phase: 'running',
      step,
      message,
      error: null,
      startedAt: Date.now(),
      etaSeconds,
    }
  }

  function updateGcodeJobStep(step: GcodeJobStep, message: string): void {
    if (gcodeJobState.value.phase !== 'running') return
    gcodeJobState.value = { ...gcodeJobState.value, step, message }
  }

  function finishGcodeJob(
    phase: Exclude<GcodeJobPhase, 'idle' | 'running'>,
    message: string,
    error: string | null = null,
  ): void {
    gcodeJobCancel.value = null
    gcodeJobState.value = {
      phase,
      step: gcodeJobState.value.step,
      message,
      error,
      startedAt: gcodeJobState.value.startedAt,
      etaSeconds: gcodeJobState.value.etaSeconds,
    }
  }

  function dismissGcodeJob(): void {
    gcodeJobCancel.value = null
    gcodeJobState.value = {
      phase: 'idle',
      step: null,
      message: '',
      error: null,
      startedAt: null,
      etaSeconds: null,
    }
  }

  function cancelGcodeJob(): void {
    const fn = gcodeJobCancel.value
    if (fn) fn()
  }

  const updateNotificationsEnabled = ref(loadUpdateNotifications())
  watch(updateNotificationsEnabled, (value) => {
    try {
      localStorage.setItem(UPDATE_NOTIFY_KEY, value ? '1' : '0')
    } catch {
      // localStorage unavailable (private browsing / quota) — preference
      // simply won't survive a reload, which is acceptable.
    }
  })

  // Plan-tab rendering preference (image / svg / auto). Persisted like the
  // notification toggle so the operator's choice survives a reload.
  const planPreviewMode = ref<PlanPreviewMode>(loadPlanPreviewMode())
  watch(planPreviewMode, (value) => {
    try {
      localStorage.setItem(PLAN_PREVIEW_KEY, value)
    } catch {
      // localStorage unavailable — preference won't persist, no-op.
    }
  })

  // Workshop camera config (System settings) — up to two stream URLs.
  // Deep watch so editing any slot's enabled / url / label re-persists the
  // whole list as JSON.
  const cameras = ref<CameraConfig[]>(loadCameras())
  watch(
    cameras,
    (value) => {
      try {
        localStorage.setItem(CAMERAS_KEY, JSON.stringify(value))
      } catch {
        // localStorage unavailable — preference won't persist, no-op.
      }
    },
    { deep: true },
  )

  function setPreviewSheet(sheet: PreviewSheet | null): void {
    previewSheet.value = sheet
  }

  function openSettings(tab?: SettingsTab): void {
    if (tab) settingsTab.value = tab
    settingsOpen.value = true
  }

  function closeSettings(): void {
    settingsOpen.value = false
  }

  // Open the independent plotter-settings modal, optionally pre-selecting
  // a sub-tab (connection / profile / colors / macros / queue).
  function openPlotterSettings(tab?: PlotterTab): void {
    if (tab) plotterTab.value = tab
    plotterSettingsOpen.value = true
  }

  function closePlotterSettings(): void {
    plotterSettingsOpen.value = false
  }

  function openEditModal(): void {
    editModalOpen.value = true
  }

  function closeEditModal(): void {
    editModalOpen.value = false
  }

  function startUpdate(message: string, etaSeconds: number | null = null): void {
    updateState.value = {
      phase: 'running',
      message,
      error: null,
      startedAt: Date.now(),
      forced: false,
      newCommitApplied: false,
      etaSeconds,
    }
  }

  function setUpdateMessage(message: string): void {
    if (updateState.value.phase === 'running') {
      updateState.value = { ...updateState.value, message }
    }
  }

  function finishUpdate(
    phase: Exclude<UpdatePhase, 'idle' | 'running'>,
    payload: {
      message: string
      error?: string | null
      forced?: boolean
      newCommitApplied?: boolean
    } = { message: '' },
  ): void {
    updateState.value = {
      phase,
      message: payload.message,
      error: payload.error ?? null,
      startedAt: updateState.value.startedAt,
      forced: payload.forced ?? false,
      newCommitApplied: payload.newCommitApplied ?? false,
      etaSeconds: updateState.value.etaSeconds,
    }
  }

  function dismissUpdate(): void {
    updateState.value = {
      phase: 'idle',
      message: '',
      error: null,
      startedAt: null,
      forced: false,
      newCommitApplied: false,
      etaSeconds: null,
    }
  }

  return {
    canvasTab,
    settingsOpen,
    settingsTab,
    plotterSettingsOpen,
    plotterTab,
    filesPanePulse,
    pulseFilesPane,
    editModalOpen,
    previewSheet,
    updateState,
    updateNotificationsEnabled,
    planPreviewMode,
    cameras,
    setPreviewSheet,
    openSettings,
    closeSettings,
    openPlotterSettings,
    closePlotterSettings,
    openEditModal,
    closeEditModal,
    startUpdate,
    setUpdateMessage,
    finishUpdate,
    dismissUpdate,
    gcodeJobState,
    gcodeJobCancel,
    startGcodeJob,
    updateGcodeJobStep,
    finishGcodeJob,
    dismissGcodeJob,
    cancelGcodeJob,
  }
})
