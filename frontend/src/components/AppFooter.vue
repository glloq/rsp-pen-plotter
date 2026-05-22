<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { computePlacement, unionBounds } from '../lib/placement'

const { t } = useI18n()
const store = useJobStore()

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const placement = computed(() => {
  const profile = store.selectedProfile
  if (!profile || store.layers.length === 0) return null
  const bounds = unionBounds(store.layers.map((l) => l.bbox))
  if (!bounds) return null
  return computePlacement(bounds, profile, store.scaleMode, store.marginMm)
})

const scaleLabel = computed(() => {
  if (!placement.value) return null
  if (store.scaleMode === 'actual') return '1:1'
  return `${(placement.value.scale * 100).toFixed(0)}%`
})

const drawingDims = computed(() => {
  const p = placement.value
  if (!p) return null
  return `${p.widthMm.toFixed(0)}×${p.heightMm.toFixed(0)} mm`
})

const exceeds = computed(() => placement.value?.exceeds ?? false)
const missing = computed(() => store.missingPenSlots)
const hasJob = computed(() => store.layers.length > 0)
</script>

<template>
  <footer
    v-if="hasJob"
    class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800 bg-slate-900/80 px-4 py-1.5 text-xs"
  >
    <div v-if="drawingDims" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.size') }}</span>
      <span class="font-mono text-slate-200">{{ drawingDims }}</span>
    </div>

    <div v-if="scaleLabel" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.scale') }}</span>
      <span class="font-mono text-slate-200">{{ scaleLabel }}</span>
    </div>

    <div class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.estimate') }}</span>
      <span class="font-mono text-slate-200">{{ formatDuration(store.totalDurationSeconds) }}</span>
    </div>

    <div v-if="store.preflight" class="flex items-baseline gap-1.5">
      <span class="text-slate-500">{{ t('footer.penChanges') }}</span>
      <span class="font-mono text-slate-200">{{ store.preflight.pen_changes }}</span>
    </div>

    <div class="ml-auto flex flex-wrap items-center gap-2">
      <span
        v-if="exceeds"
        class="rounded border border-red-700 bg-red-950/60 px-2 py-0.5 text-red-200"
      >
        ⚠ {{ t('sheet.outOfBounds') }}
      </span>
      <span
        v-if="missing.length"
        class="rounded border border-amber-700 bg-amber-950/60 px-2 py-0.5 text-amber-200"
      >
        ⚠ {{ t('preflight.missingPens', { slots: missing.join(', ') }) }}
      </span>
    </div>
  </footer>
</template>
