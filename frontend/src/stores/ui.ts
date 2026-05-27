import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type CanvasTab = 'sheet' | 'simulator' | 'gcode'
export type SettingsTab = 'system' | 'history' | 'audit' | 'slo' | 'manifests'
export type PlotterTab = 'connection' | 'profile' | 'colors' | 'macros' | 'queue'

export interface PreviewSheet {
  width_mm: number
  height_mm: number
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

export const useUiStore = defineStore('ui', () => {
  const canvasTab = ref<CanvasTab>('sheet')
  const settingsOpen = ref(false)
  const settingsTab = ref<SettingsTab>('system')
  const plotterDrawerOpen = ref(false)
  const plotterTab = ref<PlotterTab>('connection')
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
  })
  const gcodeJobCancel = ref<(() => void) | null>(null)

  function startGcodeJob(step: GcodeJobStep, message: string, cancel: () => void): void {
    gcodeJobCancel.value = cancel
    gcodeJobState.value = {
      phase: 'running',
      step,
      message,
      error: null,
      startedAt: Date.now(),
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

  function openPlotterDrawer(tab?: PlotterTab): void {
    if (tab) plotterTab.value = tab
    plotterDrawerOpen.value = true
  }

  function closePlotterDrawer(): void {
    plotterDrawerOpen.value = false
  }

  function openEditModal(): void {
    editModalOpen.value = true
  }

  function closeEditModal(): void {
    editModalOpen.value = false
  }

  function startUpdate(message: string): void {
    updateState.value = {
      phase: 'running',
      message,
      error: null,
      startedAt: Date.now(),
      forced: false,
      newCommitApplied: false,
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
    }
  }

  return {
    canvasTab,
    settingsOpen,
    settingsTab,
    plotterDrawerOpen,
    plotterTab,
    editModalOpen,
    previewSheet,
    updateState,
    updateNotificationsEnabled,
    setPreviewSheet,
    openSettings,
    closeSettings,
    openPlotterDrawer,
    closePlotterDrawer,
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
