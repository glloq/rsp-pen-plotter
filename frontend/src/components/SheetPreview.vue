<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { computePlacement, unionBounds } from '../lib/placement'

const { t } = useI18n()
const store = useJobStore()

const data = computed(() => {
  const profile = store.selectedProfile
  if (!profile || store.layers.length === 0) return null
  const bounds = unionBounds(store.layers.map((l) => l.bbox))
  if (!bounds) return null
  const placement = computePlacement(bounds, profile, store.scaleMode, store.marginMm)
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (wsW <= 0 || wsH <= 0) return null
  const pad = Math.max(wsW, wsH) * 0.04
  return { profile, placement, ws, wsW, wsH, pad }
})

const scaleLabel = computed(() => {
  if (!data.value) return ''
  if (store.scaleMode === 'actual') return '1:1'
  return `${(data.value.placement.scale * 100).toFixed(0)}%`
})
</script>

<template>
  <div
    v-if="data"
    class="mb-3 rounded-lg border border-slate-700 bg-slate-800 p-3"
  >
    <div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs">
      <h2 class="uppercase tracking-wide text-slate-400">{{ t('sheet.title') }}</h2>
      <div class="flex flex-wrap gap-x-4 gap-y-1 font-mono text-slate-300">
        <span>{{ t('sheet.sheet') }}: {{ data.wsW.toFixed(0) }}×{{ data.wsH.toFixed(0) }} mm</span>
        <span>
          {{ t('sheet.drawing') }}:
          {{ data.placement.widthMm.toFixed(0) }}×{{ data.placement.heightMm.toFixed(0) }} mm
        </span>
        <span>{{ t('sheet.scale') }}: {{ scaleLabel }}</span>
      </div>
    </div>

    <svg
      :viewBox="`${data.ws.x_min - data.pad} ${data.ws.y_min - data.pad} ${data.wsW + 2 * data.pad} ${data.wsH + 2 * data.pad}`"
      class="w-full"
      :style="{ aspectRatio: `${data.wsW + 2 * data.pad} / ${data.wsH + 2 * data.pad}`, maxHeight: '40vh' }"
      role="img"
      :aria-label="t('sheet.title')"
    >
      <rect
        :x="data.ws.x_min"
        :y="data.ws.y_min"
        :width="data.wsW"
        :height="data.wsH"
        fill="#ffffff"
        stroke="#475569"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
      <rect
        v-if="store.scaleMode === 'fit' && store.marginMm > 0"
        :x="data.ws.x_min + store.marginMm"
        :y="data.ws.y_min + store.marginMm"
        :width="Math.max(data.wsW - 2 * store.marginMm, 0)"
        :height="Math.max(data.wsH - 2 * store.marginMm, 0)"
        fill="none"
        stroke="#94a3b8"
        stroke-width="1"
        stroke-dasharray="4 3"
        vector-effect="non-scaling-stroke"
      />
      <rect
        :x="data.placement.footprint.x_min"
        :y="data.placement.footprint.y_min"
        :width="data.placement.footprint.x_max - data.placement.footprint.x_min"
        :height="data.placement.footprint.y_max - data.placement.footprint.y_min"
        :fill="data.placement.exceeds ? 'rgba(220,38,38,0.18)' : 'rgba(16,185,129,0.18)'"
        :stroke="data.placement.exceeds ? '#dc2626' : '#10b981'"
        stroke-width="1.5"
        vector-effect="non-scaling-stroke"
      />
    </svg>

    <p v-if="data.placement.exceeds" class="mt-2 text-xs text-red-400">
      {{ t('sheet.outOfBounds') }}
    </p>
  </div>
</template>
