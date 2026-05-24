<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth, systemCheckUpdate } from './api/client'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import CanvasView from './components/CanvasView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import EditModal from './components/EditModal.vue'
import FilesPane from './components/FilesPane.vue'
import PlotterDrawer from './components/PlotterDrawer.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import Toasts from './components/Toasts.vue'
import UpdateProgressModal from './components/UpdateProgressModal.vue'
import { useJobStore } from './stores/job'
import { useLibraryStore } from './stores/library'
import { useToastStore } from './stores/toasts'
import { useUiStore } from './stores/ui'

const { t, locale } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const ui = useUiStore()
const toasts = useToastStore()
const dragDepth = ref(0)
const dropping = ref(false)

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

onMounted(async () => {
  window.addEventListener('dragenter', onWindowDragEnter)
  window.addEventListener('dragleave', onWindowDragLeave)
  window.addEventListener('dragover', onWindowDragOver)
  window.addEventListener('drop', onWindowDrop)
  try {
    await getHealth()
    await Promise.all([store.loadProfiles(), store.loadPresets()])
  } catch {
    toasts.error(t('app.apiUnreachable'))
  }
  // Fire-and-forget: the toast is purely advisory, no need to block the
  // rest of the startup sequence on the (potentially slow) git fetch.
  void checkForUpdatesOnStartup()
})

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onWindowDragEnter)
  window.removeEventListener('dragleave', onWindowDragLeave)
  window.removeEventListener('dragover', onWindowDragOver)
  window.removeEventListener('drop', onWindowDrop)
})
</script>

<template>
  <div class="flex h-screen flex-col bg-slate-900 text-slate-100">
    <AppHeader />

    <main
      class="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]"
    >
      <FilesPane />
      <CanvasView />
    </main>

    <AppFooter />
    <SettingsDrawer />
    <PlotterDrawer />
    <EditModal />
    <ConfirmDialog />
    <UpdateProgressModal />
    <Toasts />

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
