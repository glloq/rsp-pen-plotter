<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore } from '../stores/ui'
import MachineStatusPill from './MachineStatusPill.vue'

defineProps<{
  status: string | null
  version: string | null
  apiError: boolean
}>()

const { t } = useI18n()
const ui = useUiStore()
const plotter = usePlotterStore()
const { status: plotterStatus } = storeToRefs(plotter)
</script>

<template>
  <header
    class="flex flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900/95 px-4 py-2 backdrop-blur"
  >
    <div class="mr-2 flex items-baseline gap-2">
      <h1 class="text-lg font-bold tracking-tight">OmniPlot</h1>
      <p class="hidden text-xs text-slate-500 lg:block">{{ t('app.tagline') }}</p>
    </div>

    <div class="ml-auto flex items-center gap-3">
      <button
        type="button"
        class="flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition"
        :class="plotterStatus.connected
          ? 'border-emerald-700 bg-emerald-950/40 text-emerald-200 hover:bg-emerald-900/40'
          : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'"
        :title="t('header.plotter')"
        :aria-label="t('header.plotter')"
        @click="ui.openPlotterDrawer()"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-4 w-4">
          <rect x="3" y="6" width="18" height="12" rx="1" />
          <path d="M7 10h10" />
          <path d="M12 14v4" />
          <circle cx="7" cy="14" r="0.5" />
        </svg>
        <span class="hidden sm:inline">{{ t('header.plotter') }}</span>
        <MachineStatusPill />
      </button>

      <button
        type="button"
        class="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        :title="t('header.settings')"
        :aria-label="t('header.settings')"
        @click="ui.openSettings()"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="h-4 w-4">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
        <span class="hidden sm:inline">{{ t('header.settings') }}</span>
      </button>

      <span
        v-if="apiError"
        class="rounded bg-red-900/60 border border-red-500 px-2 py-1 text-xs text-red-200"
      >
        {{ t('app.apiUnreachable') }}
      </span>
      <span
        v-else-if="status"
        class="hidden font-mono text-[10px] text-emerald-400/70 lg:inline"
        :title="`v${version}`"
      >
        API {{ status }}
      </span>
    </div>
  </header>
</template>
