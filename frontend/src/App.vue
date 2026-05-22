<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth } from './api/client'
import FileUpload from './components/FileUpload.vue'
import GcodePreview from './components/GcodePreview.vue'
import LayerPanel from './components/LayerPanel.vue'
import PlotterPanel from './components/PlotterPanel.vue'
import Simulator from './components/Simulator.vue'
import SvgPreview from './components/SvgPreview.vue'
import { useJobStore } from './stores/job'

const store = useJobStore()
const status = ref<string | null>(null)
const version = ref<string | null>(null)
const apiError = ref(false)

onMounted(async () => {
  try {
    const health = await getHealth()
    status.value = health.status
    version.value = health.version
    await store.loadProfiles()
  } catch {
    apiError.value = true
  }
})
</script>

<template>
  <div class="min-h-screen bg-slate-900 text-slate-100">
    <header class="flex items-center justify-between border-b border-slate-800 px-6 py-3">
      <h1 class="text-xl font-bold tracking-tight">OmniPlot</h1>
      <span
        v-if="apiError"
        class="rounded bg-red-900/60 border border-red-500 px-2 py-1 text-xs text-red-200"
      >
        API unreachable
      </span>
      <span v-else-if="status" class="font-mono text-xs text-emerald-300">
        API: {{ status }} (v{{ version }})
      </span>
    </header>

    <main class="grid grid-cols-1 gap-4 p-6 lg:grid-cols-[320px_1fr]">
      <aside class="space-y-4">
        <FileUpload />
        <LayerPanel />
        <PlotterPanel />
      </aside>
      <section>
        <SvgPreview />
        <Simulator />
        <GcodePreview />
      </section>
    </main>
  </div>
</template>
