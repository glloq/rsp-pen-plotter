<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth } from './api/client'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import CanvasView from './components/CanvasView.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import ExecutePane from './components/ExecutePane.vue'
import PreparePane from './components/PreparePane.vue'
import SettingsDrawer from './components/SettingsDrawer.vue'
import { useJobStore } from './stores/job'

const { locale } = useI18n()
const store = useJobStore()
const status = ref<string | null>(null)
const version = ref<string | null>(null)
const apiError = ref(false)

watch(
  locale,
  (value) => {
    document.documentElement.setAttribute('lang', value)
  },
  { immediate: true },
)

onMounted(async () => {
  try {
    const health = await getHealth()
    status.value = health.status
    version.value = health.version
    await Promise.all([store.loadProfiles(), store.loadPresets()])
  } catch {
    apiError.value = true
  }
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
  </div>
</template>
