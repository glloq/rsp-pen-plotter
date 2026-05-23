<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth } from './api/client'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import CanvasView from './components/CanvasView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ExecutePane from './components/ExecutePane.vue'
import PreparePane from './components/PreparePane.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import Toasts from './components/Toasts.vue'
import { useJobStore } from './stores/job'
import { useToastStore } from './stores/toasts'

const { t, locale } = useI18n()
const store = useJobStore()
const toasts = useToastStore()
const status = ref<string | null>(null)
const version = ref<string | null>(null)
const apiError = ref(false)
const dragDepth = ref(0)
const dropping = ref(false)

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
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  event.preventDefault()
  await store.upload(file)
  if (store.layers.length) {
    toasts.success(
      t('toast.uploaded', { name: file.name, count: store.layers.length }),
      4000,
    )
  }
}

onMounted(async () => {
  window.addEventListener('dragenter', onWindowDragEnter)
  window.addEventListener('dragleave', onWindowDragLeave)
  window.addEventListener('dragover', onWindowDragOver)
  window.addEventListener('drop', onWindowDrop)
  try {
    const health = await getHealth()
    status.value = health.status
    version.value = health.version
    await Promise.all([store.loadProfiles(), store.loadPresets()])
  } catch {
    apiError.value = true
  }
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
    <AppHeader :status="status" :version="version" :api-error="apiError" />

    <main
      class="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[300px_minmax(0,1fr)_300px] xl:grid-cols-[320px_minmax(0,1fr)_340px]"
    >
      <PreparePane />
      <CanvasView />
      <ExecutePane />
    </main>

    <AppFooter />
    <SettingsDrawer />
    <ConfirmDialog />
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
