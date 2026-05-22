<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { usePlotterStore } from '../stores/plotter'

const { t } = useI18n()
const plotter = usePlotterStore()
const { status, progress } = storeToRefs(plotter)

type Tone = 'idle' | 'busy' | 'warn' | 'off'

const view = computed<{ tone: Tone; label: string; sub: string | null }>(() => {
  if (!status.value.connected) {
    return { tone: 'off', label: t('machine.disconnected'), sub: null }
  }
  switch (status.value.state) {
    case 'running':
      return {
        tone: 'busy',
        label: t('machine.running'),
        sub: `${Math.round(progress.value * 100)}%`,
      }
    case 'paused':
      return { tone: 'warn', label: t('machine.paused'), sub: null }
    case 'waiting':
      return { tone: 'warn', label: t('machine.toolChange'), sub: null }
    case 'error':
      return { tone: 'warn', label: t('machine.error'), sub: null }
    default:
      return { tone: 'idle', label: t('machine.idle'), sub: null }
  }
})

const toneClass: Record<Tone, string> = {
  idle: 'border-emerald-700 bg-emerald-950/50 text-emerald-200',
  busy: 'border-sky-700 bg-sky-950/50 text-sky-200',
  warn: 'border-amber-700 bg-amber-950/50 text-amber-200',
  off: 'border-slate-700 bg-slate-800 text-slate-400',
}

const dotClass: Record<Tone, string> = {
  idle: 'bg-emerald-400',
  busy: 'bg-sky-400 animate-pulse',
  warn: 'bg-amber-400 animate-pulse',
  off: 'bg-slate-500',
}
</script>

<template>
  <div
    class="flex items-center gap-2 rounded-full border px-3 py-1 text-xs"
    :class="toneClass[view.tone]"
  >
    <span class="h-2 w-2 rounded-full" :class="dotClass[view.tone]" />
    <span class="font-medium">{{ view.label }}</span>
    <span v-if="view.sub" class="font-mono text-[10px] opacity-80">{{ view.sub }}</span>
  </div>
</template>
