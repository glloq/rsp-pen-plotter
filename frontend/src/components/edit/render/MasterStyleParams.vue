<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  resolveMasterStyle,
  type SegmentationMethod,
} from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

// Per-style knobs exposed by the active master style. Two paths:
//   - shaded styles (luminance_bands)   → bands slider (2..6)
//   - binary styles (thresholds)        → single threshold slider
//                                          (0.1..0.9)
//
// All other style state (pen slot, detail level) lives in its own
// shared component so a future style with new knobs only needs an
// addition here, not a copy of the whole MonochromeCard.

interface BitmapLike {
  num_bands: number
  thresholds: number[]
  segmentation_method: SegmentationMethod
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
  styleId: string
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

const style = computed(() => resolveMasterStyle(props.styleId))
const usesBands = computed(
  () => style.value.segmentation?.method === 'luminance_bands',
)

const thresholdValue = computed({
  get: () => props.bitmap.thresholds[0] ?? 0.5,
  set: (v: number) => {
    props.bitmap.thresholds = [Math.max(0, Math.min(1, v))]
    draft.markSegmentationTouched('thresholds')
  },
})

function setNumBands(value: number): void {
  props.bitmap.num_bands = value
  draft.markSegmentationTouched('num_bands')
}
</script>

<template>
  <div v-if="usesBands" class="space-y-1">
    <div class="flex items-center justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('mono.shades') }}
        <LayerCountBadge :count="draft.expectedLayerCount.value" />
      </p>
      <span class="font-mono text-[11px] text-slate-300">{{ bitmap.num_bands }}</span>
    </div>
    <input
      :value="bitmap.num_bands"
      type="range"
      min="1"
      max="6"
      step="1"
      class="w-full accent-emerald-500"
      @input="(e) => setNumBands(Number((e.target as HTMLInputElement).value))"
    />
    <p class="text-[10px] text-slate-500">{{ t('mono.shadesHint') }}</p>
  </div>

  <div v-else class="space-y-1">
    <div class="flex items-center justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('mono.threshold') }}
        <LayerCountBadge :count="draft.expectedLayerCount.value" />
      </p>
      <span class="font-mono text-[11px] text-slate-300">{{ thresholdValue.toFixed(2) }}</span>
    </div>
    <input
      v-model.number="thresholdValue"
      type="range"
      min="0.1"
      max="0.9"
      step="0.05"
      class="w-full accent-emerald-500"
    />
    <p class="text-[10px] text-slate-500">{{ t('mono.thresholdHint') }}</p>
  </div>
</template>
