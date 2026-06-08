<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth, systemCheckUpdate } from './api/client'
import AppHeader from './components/AppHeader.vue'
import CanvasView from './components/CanvasView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import FilesPane from './components/FilesPane.vue'
import PlotterSettingsModal from './components/PlotterSettingsModal.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import SwapPromptModal from './components/SwapPromptModal.vue'
import Toasts from './components/Toasts.vue'
import UpdateProgressModal from './components/UpdateProgressModal.vue'
import GenerateProgressModal from './components/GenerateProgressModal.vue'
import UploadProgressModal from './components/UploadProgressModal.vue'
import IntegrityBanner from './components/IntegrityBanner.vue'
import ManifestFallbackBanner from './components/ManifestFallbackBanner.vue'

// Lazy-load v2 surfaces that aren't on the boot critical path. Each
// gets its own chunk, fetched only the first time the operator
// triggers it: opens the V2 modal, toggles Workshop Mode, or
// activates the perf overlay flag. Saves ~150 kB from the initial
// parse on a fresh load.
const EditModalV2 = defineAsyncComponent(() => import('./components/v2/EditModalV2.vue'))
const WorkshopMode = defineAsyncComponent(() => import('./components/v2/WorkshopMode.vue'))
const PerfOverlay = defineAsyncComponent(() => import('./components/v2/PerfOverlay.vue'))

import { api } from './api/client'
import { useAlgorithmsStore } from './stores/algorithms'
import { useFeatureFlag } from './composables/useFeatureFlag'
import { useJobStore } from './stores/job'
import { useKeyboardShortcuts } from './composables/useKeyboardShortcuts'
import { useLibraryStore } from './stores/library'
import { usePerfStore } from './stores/perf'
import { useQueueStore } from './stores/queue'
import { useToastStore } from './stores/toasts'
import { useUiModeStore } from './stores/uiMode'
import { useUiStore } from './stores/ui'
import { useUploadsStore } from './stores/uploads'

const { t, locale } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const ui = useUiStore()
const uiMode = useUiModeStore()
const toasts = useToastStore()
const algorithms = useAlgorithmsStore()
const perf = usePerfStore()
const queue = useQueueStore()
const uploads = useUploadsStore()
const dragDepth = ref(0)
const dropping = ref(false)

// Feature-flagged v2 surfaces. ``?flag.workshopMode=1`` (or the header
// button below) opens the full-screen run cockpit. The perf overlay
// mounts inconditionally — it auto-hides when its own flag is off.
// The Edit modal is always the V2 wizard since the v0.2 migration; the
// Assisted/Expert UX mode now only controls per-section disclosure
// inside the wizard, not which editor is shown.
const workshopEnabled = useFeatureFlag('workshopMode')
const perfEnabled = useFeatureFlag('perf')
const activeRun = computed(() => queue.active[0] ?? null)

function onEditV2Cancel(): void {
  ui.closeEditModal()
}
async function onEditV2Confirm(
  decision: import('./domain/policy/schemas').PolicyDecision,
): Promise<void> {
  // Propagate the resolver recommendation to every layer of the
  // selected placement, then trigger a single rerender so the canvas
  // catches up. ``applyAlgorithmToAllLayers`` debounces internally so
  // a missed-click double-confirm is safe. The placement must exist
  // — the modal only opens when one is selected. Failures are
  // surfaced via the existing rerender error path; we don't need to
  // duplicate them here.
  // QUALITY recommendations ship a multi-pass stack (e.g. double-pass
  // crosshatch); apply it as passes so Generate matches the preview.
  // Everything else stays a single algorithm across all layers.
  const passes = decision.default_passes ?? []
  if (passes.length) {
    await store.applyPassesToAllLayers(passes)
  } else {
    await store.applyAlgorithmToAllLayers(
      decision.default_algorithm,
      (decision.default_options ?? {}) as Record<string, unknown>,
    )
  }
  ui.closeEditModal()
}
// Map the placement's MIME to a ``SourceKind`` so the V2 wizard pre-
// selects the right value. Falls back to ``bitmap_photo`` (the most
// common upload) when the placement isn't selected yet.
const v2SourceKind = computed<import('./domain/policy/schemas').SourceKind>(() => {
  const mime = store.selectedPlacement?.source_mime ?? ''
  if (mime === 'image/svg+xml') return 'vector_svg'
  if (mime === 'application/pdf') return 'pdf_doc'
  if (mime.startsWith('image/')) return 'bitmap_photo'
  return 'bitmap_photo'
})
const v2AvailableColorsCount = computed(() => store.selectedProfile?.pen_slot_count ?? 1)
const v2IsMonoPenMachine = computed(() => (store.selectedProfile?.pen_slot_count ?? 1) <= 1)

function closeWorkshop(): void {
  uiMode.setFlag('workshopMode', false)
}
async function workshopPause(): Promise<void> {
  const run = activeRun.value
  if (run) await queue.act(run.id, 'pause')
}
async function workshopResume(): Promise<void> {
  const run = activeRun.value
  if (run) await queue.act(run.id, 'resume')
}

useKeyboardShortcuts([
  { id: 'mode.toggle', handler: () => uiMode.toggleMode() },
  {
    id: 'perf.toggle',
    handler: () => uiMode.setFlag('perf', !uiMode.isFlagEnabled('perf')),
  },
  {
    id: 'queue.pause',
    handler: () => {
      const run = activeRun.value
      if (run && run.state === 'running') void queue.act(run.id, 'pause')
    },
  },
  {
    id: 'queue.resume',
    handler: () => {
      const run = activeRun.value
      if (run && run.state === 'paused') void queue.act(run.id, 'resume')
    },
  },
])

async function checkForUpdatesOnStartup(): Promise<void> {
  // Honour the opt-out toggle in Settings › System.
  if (!ui.updateNotificationsEnabled) return
  try {
    const result = await systemCheckUpdate()
    if (!result.update_available) return
    let toastId = 0
    toastId = toasts.show(
      'info',
      t('toast.updateAvailable', { count: result.behind }),
      // Long-lived: the operator should be able to read it after wandering
      // back to the tab. Stays until dismissed or the action is clicked.
      0,
      {
        label: t('toast.openSettings'),
        onClick: () => {
          ui.openSettings('system')
          toasts.dismiss(toastId)
        },
      },
    )
  } catch {
    // Offline appliance / no network — silent. The Settings › System panel
    // surfaces version errors there if the user goes looking.
  }
}

watch(
  locale,
  (value) => {
    document.documentElement.setAttribute('lang', value)
  },
  { immediate: true },
)

function onWindowDragEnter(event: DragEvent): void {
  if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return
  dragDepth.value += 1
  dropping.value = true
}

function onWindowDragLeave(event: DragEvent): void {
  if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
  if (dragDepth.value === 0) dropping.value = false
}

function onWindowDragOver(event: DragEvent): void {
  if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return
  event.preventDefault()
}

async function onWindowDrop(event: DragEvent): Promise<void> {
  dragDepth.value = 0
  dropping.value = false
  // SourceSection's drop zone calls preventDefault on its own drop; in that
  // case we let it handle the upload and skip here to avoid uploading twice.
  if (event.defaultPrevented) return
  const files = Array.from(event.dataTransfer?.files ?? [])
  if (!files.length) return
  event.preventDefault()
  // Drops add the files to the library only — no placement is created
  // and the editor stays closed. The operator picks what to do next from
  // the Files pane (drag onto the plan, edit, etc.). The uploads store
  // owns validation, the concurrency pool and the progress modal.
  uploads.start(files)
}

// Axios error interceptor — feeds the ``network_error`` KPI in the
// perf overlay (roadmap B.2 wire). Installed once after Pinia is alive
// so the lazy ``usePerfStore`` call is safe. Aborted requests don't
// count as errors (the operator asked).
let perfInterceptorId: number | null = null

onMounted(async () => {
  window.addEventListener('dragenter', onWindowDragEnter)
  window.addEventListener('dragleave', onWindowDragLeave)
  window.addEventListener('dragover', onWindowDragOver)
  window.addEventListener('drop', onWindowDrop)

  if (perfInterceptorId === null) {
    perfInterceptorId = api.interceptors.response.use(
      (response) => response,
      (error) => {
        const isCancelled =
          (error as { name?: string; code?: string })?.name === 'CanceledError' ||
          (error as { code?: string })?.code === 'ERR_CANCELED'
        if (!isCancelled) {
          perf.record({
            kpi: 'network_error',
            value: 1,
            recorded_at: Date.now(),
            label: (error as { config?: { url?: string } })?.config?.url,
          })
        }
        return Promise.reject(error)
      },
    )
  }
  try {
    await getHealth()
    await Promise.all([store.loadProfiles(), store.loadPresets()])
  } catch {
    // Backend unreachable at boot is operator-blocking: nothing in the
    // app works without it. Use the persistent ``critical`` channel so
    // the toast survives the standard 6 s timer and the operator can
    // see it after wandering away from the screen.
    toasts.critical(t('app.apiUnreachable'))
  }
  // Fire-and-forget: the toast is purely advisory, no need to block the
  // rest of the startup sequence on the (potentially slow) git fetch.
  void checkForUpdatesOnStartup()
  // Library integrity is best-effort: the banner stays hidden when the
  // call fails, so a transient network blip never turns into a false
  // alert. Refreshed only on boot — the backend boot scan is the
  // authoritative trigger.
  void library.refreshIntegrity()
  // Algorithm manifest powers the v2 modal's resolver UI and the
  // fallback banner. Failure populates `source` with 'snapshot' so the
  // banner becomes visible — no toast needed.
  void algorithms.refresh()
  // Queue polling needs to run for the whole app session so Workshop
  // Mode + WorkspaceRail see live runs even when the operator never
  // opens the Plotter tab. ``startPolling`` is idempotent — calling
  // it again from PlotterControl is a no-op.
  queue.startPolling()
})

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onWindowDragEnter)
  window.removeEventListener('dragleave', onWindowDragLeave)
  window.removeEventListener('dragover', onWindowDragOver)
  window.removeEventListener('drop', onWindowDrop)
  if (perfInterceptorId !== null) {
    api.interceptors.response.eject(perfInterceptorId)
    perfInterceptorId = null
  }
})
</script>

<template>
  <div class="flex h-screen flex-col bg-slate-900 text-slate-100">
    <AppHeader />
    <ManifestFallbackBanner
      v-if="algorithms.source"
      :source="algorithms.source"
      :error="algorithms.lastError ?? undefined"
    />
    <IntegrityBanner />

    <main
      class="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]"
    >
      <FilesPane />
      <CanvasView />
    </main>

    <SettingsDrawer />
    <PlotterSettingsModal />
    <!-- Edit modal — V2 wizard is the only surface (v0.2 migration).
         ``:key`` re-mounts when the operator switches files so local
         state (sourceKind, goal, decision, …) resets to defaults
         derived from the new placement. -->
    <EditModalV2
      v-if="ui.editModalOpen"
      :key="store.selectedPlacement?.id ?? 'no-placement'"
      :initial-source-kind="v2SourceKind"
      :available-colors-count="v2AvailableColorsCount"
      :is-mono-pen-machine="v2IsMonoPenMachine"
      :layers="store.selectedPlacement?.layers ?? []"
      :source-name="store.selectedPlacement?.source_file"
      :preview-svg="store.selectedPlacement?.svg"
      @cancel="onEditV2Cancel"
      @confirm="onEditV2Confirm"
    />
    <ConfirmDialog />
    <UpdateProgressModal />
    <GenerateProgressModal />
    <UploadProgressModal />
    <SwapPromptModal />
    <Toasts />
    <PerfOverlay v-if="perfEnabled" />
    <WorkshopMode
      v-if="workshopEnabled"
      :run="activeRun"
      :next-action-hint="activeRun?.swap_prompt ?? null"
      @exit="closeWorkshop"
      @pause="workshopPause"
      @resume="workshopResume"
    />

    <div
      v-if="dropping"
      class="pointer-events-none fixed inset-0 z-30 flex items-center justify-center bg-emerald-950/70 backdrop-blur-sm"
    >
      <div
        class="pointer-events-none rounded-2xl border-4 border-dashed border-emerald-400 bg-slate-900/80 px-12 py-8 text-center"
      >
        <p class="text-4xl">⤵</p>
        <p class="mt-2 text-lg font-semibold text-emerald-200">{{ t('app.dropToImport') }}</p>
        <p class="text-xs text-emerald-300/70">{{ t('app.dropHint') }}</p>
      </div>
    </div>
  </div>
</template>
