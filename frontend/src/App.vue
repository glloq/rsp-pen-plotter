<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getHealth } from './api/client'
import FileUpload from './components/FileUpload.vue'
import GcodePreview from './components/GcodePreview.vue'
import JobHistory from './components/JobHistory.vue'
import LayerPanel from './components/LayerPanel.vue'
import MacroPanel from './components/MacroPanel.vue'
import PlotterPanel from './components/PlotterPanel.vue'
import ProfileEditor from './components/ProfileEditor.vue'
import Simulator from './components/Simulator.vue'
import SvgPreview from './components/SvgPreview.vue'
import { useJobStore } from './stores/job'

const { t, locale } = useI18n()
const store = useJobStore()
const status = ref<string | null>(null)
const version = ref<string | null>(null)
const apiError = ref(false)

// The canvas simulator only understands G-code (G0/G1); EBB output isn't G-code.
const canSimulate = computed(() => store.selectedProfile?.gcode_dialect !== 'ebb')

function setLocale(value: string): void {
  locale.value = value
}

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
  <div class="min-h-screen bg-slate-900 text-slate-100">
    <header class="flex items-center justify-between border-b border-slate-800 px-6 py-3">
      <div>
        <h1 class="text-xl font-bold tracking-tight">OmniPlot</h1>
        <p class="text-xs text-slate-500">{{ t('app.tagline') }}</p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex overflow-hidden rounded border border-slate-700 text-xs">
          <button
            class="px-2 py-1"
            :class="locale === 'en' ? 'bg-slate-700 text-white' : 'text-slate-400'"
            @click="setLocale('en')"
          >
            EN
          </button>
          <button
            class="px-2 py-1"
            :class="locale === 'fr' ? 'bg-slate-700 text-white' : 'text-slate-400'"
            @click="setLocale('fr')"
          >
            FR
          </button>
        </div>
        <span
          v-if="apiError"
          class="rounded bg-red-900/60 border border-red-500 px-2 py-1 text-xs text-red-200"
        >
          {{ t('app.apiUnreachable') }}
        </span>
        <span v-else-if="status" class="font-mono text-xs text-emerald-300">
          API: {{ status }} (v{{ version }})
        </span>
      </div>
    </header>

    <main class="grid grid-cols-1 gap-4 p-6 lg:grid-cols-[320px_1fr]">
      <aside class="space-y-4">
        <FileUpload />
        <ProfileEditor />
        <LayerPanel />
        <PlotterPanel />
        <MacroPanel />
        <JobHistory />
      </aside>
      <section>
        <SvgPreview />
        <Simulator v-if="canSimulate" />
        <GcodePreview />
      </section>
    </main>
  </div>
</template>
