<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const job = useJobStore()
const ui = useUiStore()

const slots = computed(() => {
  const profile = job.selectedProfile
  if (!profile) return []
  const pens = profile.pens ?? []
  const used = new Set(job.layers.map((l) => l.target_pen_slot).filter((s): s is number => s !== null))
  return Array.from({ length: profile.pen_slot_count }, (_, i) => {
    const pen = pens.find((p) => p.index === i)
    return {
      index: i,
      name: pen?.name || `${i}`,
      color: pen?.color ?? '#94a3b8',
      installed: pen ? pen.installed : true,
      missing: job.missingPenSlots.includes(i),
      used: used.has(i),
    }
  })
})
</script>

<template>
  <div
    v-if="slots.length"
    class="flex flex-wrap items-center gap-1.5 border-t border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs"
  >
    <span class="text-slate-500">{{ t('pens.magazine') }}</span>
    <button
      v-for="slot in slots"
      :key="slot.index"
      type="button"
      class="flex items-center gap-1 rounded border px-1.5 py-0.5 transition"
      :class="[
        slot.missing
          ? 'border-amber-600 bg-amber-950/40 text-amber-200'
          : slot.used
            ? 'border-slate-600 bg-slate-800 text-slate-200'
            : 'border-slate-700 bg-slate-900/50 text-slate-400 opacity-70',
        !slot.installed && !slot.missing ? 'opacity-50' : '',
      ]"
      :title="t('pens.tooltip', { index: slot.index, name: slot.name, status: slot.installed ? t('pens.installed') : t('pens.notInstalled') })"
      @click="ui.openSettings('profile')"
    >
      <span class="font-mono text-[10px] text-slate-500">{{ slot.index }}</span>
      <span
        class="h-3 w-3 rounded-full border border-slate-600"
        :style="{ backgroundColor: slot.color }"
      />
      <span class="max-w-[6rem] truncate">{{ slot.name }}</span>
      <span v-if="slot.missing" class="text-amber-300">⚠</span>
    </button>
  </div>
</template>
