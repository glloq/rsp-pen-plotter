<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth, systemCheckUpdate } from './api/client'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import CanvasView from './components/CanvasView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import EditModal from './components/EditModal.vue'
import CompareView, { type Candidate } from './components/v2/CompareView.vue'
import EditModalV2 from './components/v2/EditModalV2.vue'
import WorkspaceRail from './components/v2/WorkspaceRail.vue'
import FilesPane from './components/FilesPane.vue'
import PlotterDrawer from './components/PlotterDrawer.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import Toasts from './components/Toasts.vue'
import UpdateProgressModal from './components/UpdateProgressModal.vue'
import GenerateProgressModal from './components/GenerateProgressModal.vue'
import IntegrityBanner from './components/IntegrityBanner.vue'
import ManifestFallbackBanner from './components/ManifestFallbackBanner.vue'
import PerfOverlay from './components/v2/PerfOverlay.vue'
import WorkshopMode from './components/v2/WorkshopMode.vue'
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

const { t, locale } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const ui = useUiStore()
const uiMode = useUiModeStore()
const toasts = useToastStore()
const algorithms = useAlgorithmsStore()
const perf = usePerfStore()
const queue = useQueueStore()
const dragDepth = ref(0)
const dropping = ref(false)

// Feature-flagged v2 surfaces. Each is opt-in: ?flag.modalV2=1 enables
// the six-step modal alongside v1, ?flag.workshopMode=1 (or the header
// button below) opens the full-screen run cockpit. The perf overlay
// mounts inconditionally — it auto-hides when its own flag is off.
const modalV2Enabled = useFeatureFlag('modalV2')
const workshopEnabled = useFeatureFlag('workshopMode')
const compareEnabled = useFeatureFlag('compareMode')
const activeRun = computed(() => queue.active[0] ?? null)

// Compare drawer (roadmap C.5). Entry button is gated by the
// `compareMode` flag; opens a modal showing CompareView for two
// variants of the current placement. Rendering each variant
// independently requires a re-render per variant (the placement only
// holds the active variant's SVG today) — the seam is wired so the
// operator can drive the workflow; full per-variant rendering lands
// with the overlay PR.
const compareOpen = ref(false)
const compareCandidates = computed<{ a: Candidate; b: Candidate } | null>(() => {
  const placement = store.selectedPlacement
  if (!placement || placement.variants.length < 2) return null
  const v1 = placement.variants[0]
  const v2 = placement.variants[1]
  if (!v1 || !v2) return null
  const make = (variantId: string, label: string): Candidate => ({
    id: variantId,
    label,
    svg: placement.svg,
    decision: null,
    metrics: {},
  })
  return {
    a: make(v1.id, v1.name || 'Variante A'),
    b: make(v2.id, v2.name || 'Variante B'),
  }
})

function onEditV2Cancel(): void {
  ui.closeEditModal()
}
function onEditV2Confirm(): void {
  // Wiring the resolver decision back into the placement draft lands
  // with the v2 modal cut-over — until then, confirm just closes so the
  // operator isn't trapped in the flow.
  ui.closeEditModal()
}

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
  // the Files pane (drag onto the plan, edit, etc.).
  for (const file of files) {
    await library.upload(file)
  }
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
    toasts.error(t('app.apiUnreachable'))
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
      class="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[280px_minmax(0,1fr)_auto] xl:grid-cols-[320px_minmax(0,1fr)_auto]"
    >
      <FilesPane />
      <CanvasView />
      <WorkspaceRail />
    </main>

    <AppFooter />
    <SettingsDrawer />
    <PlotterDrawer />
    <!-- Edit modal: v2 is mounted alongside v1 behind ?flag.modalV2=1
         so it can be QA'd in production builds without affecting the
         default operator flow. Cut-over happens once the v2 confirm
         path is wired into the placement draft (follow-up). -->
    <EditModal v-if="!modalV2Enabled" />
    <EditModalV2
      v-else-if="ui.editModalOpen"
      :layers="store.selectedPlacement?.layers ?? []"
      @cancel="onEditV2Cancel"
      @confirm="onEditV2Confirm"
    />
    <ConfirmDialog />
    <UpdateProgressModal />
    <GenerateProgressModal />
    <Toasts />
    <PerfOverlay />
    <WorkshopMode
      v-if="workshopEnabled"
      :run="activeRun"
      @exit="closeWorkshop"
      @pause="workshopPause"
      @resume="workshopResume"
    />

    <!-- Compare drawer (roadmap C.5) — gated behind ?flag.compareMode=1
         to keep the v0.1 layout untouched. -->
    <button
      v-if="compareEnabled"
      type="button"
      class="fixed bottom-3 left-3 z-30 flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 shadow-lg hover:bg-slate-700"
      data-test="compare-open"
      @click="compareOpen = true"
    >
      ⇄ {{ t('compare.open') }}
    </button>
    <div
      v-if="compareEnabled && compareOpen"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
      data-test="compare-modal"
      @click.self="compareOpen = false"
    >
      <div class="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-xl border border-slate-700 bg-white p-4 shadow-2xl">
        <header class="mb-2 flex items-center justify-between">
          <h2 class="text-base font-semibold text-slate-900">
            {{ t('compare.title') }}
          </h2>
          <button
            type="button"
            class="rounded p-1 text-slate-500 hover:bg-slate-100"
            :aria-label="t('settings.close')"
            @click="compareOpen = false"
          >
            ✕
          </button>
        </header>
        <CompareView
          v-if="compareCandidates"
          :a="compareCandidates.a"
          :b="compareCandidates.b"
        />
        <p v-else class="text-sm text-slate-600">
          {{ t('compare.empty') }}
        </p>
      </div>
    </div>

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
