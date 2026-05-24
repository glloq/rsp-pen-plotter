<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SegmentationMethod } from '../../../api/client'

// Segmentation card: how the bitmap is split into colour layers
// (kmeans / luminance_bands / thresholds / fixed_palette) plus the
// post-processing knobs (min region, merge delta-E, background drop,
// max dimension). The bitmap reactive object is passed by reference so
// children mutate fields directly — the parent's deep watcher picks
// up changes and reschedules /preview.

interface BitmapDraft {
  segmentation_method: SegmentationMethod
  num_colors: number
  num_bands: number
  thresholds: number[]
  palette: string[]
  min_region_pixels: number
  merge_delta_e: number
  max_dimension_px: number
  drop_background: boolean
  background_luminance: number
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapDraft
  // When true, surface a hint that segmentation only acts on the
  // embedded raster portion of the document (PDF / DOCX / SVG image
  // tags), not the vector content.
  isDocument: boolean
}>()

const { t } = useI18n()

const expanded = ref(true)
const SEG_METHODS: SegmentationMethod[] = ['kmeans', 'luminance_bands', 'thresholds', 'fixed_palette']

// Detail tiers shared with MonochromeCard so the vocabulary stays
// consistent. Pixel values are kept as implementation detail; the
// UI only shows the named tier.
interface DetailLevel {
  id: 'low' | 'standard' | 'high' | 'max'
  value: number
  labelKey: string
}
const detailLevels: DetailLevel[] = [
  { id: 'low', value: 400, labelKey: 'mono.detailLow' },
  { id: 'standard', value: 800, labelKey: 'mono.detailStandard' },
  { id: 'high', value: 1400, labelKey: 'mono.detailHigh' },
  { id: 'max', value: 2400, labelKey: 'mono.detailMax' },
]
const currentDetail = computed<DetailLevel['id']>(() => {
  const target = props.bitmap.max_dimension_px
  let best = detailLevels[0]!
  let bestDelta = Math.abs(best.value - target)
  for (const level of detailLevels.slice(1)) {
    const delta = Math.abs(level.value - target)
    if (delta < bestDelta) {
      best = level
      bestDelta = delta
    }
  }
  return best.id
})

function addThreshold(): void {
  props.bitmap.thresholds = [...props.bitmap.thresholds, 0.5].sort((a, b) => a - b)
}
function removeThreshold(i: number): void {
  props.bitmap.thresholds = props.bitmap.thresholds.filter((_, idx) => idx !== i)
}
function updateThreshold(i: number, value: number): void {
  const clamped = Math.max(0, Math.min(1, value))
  const next = [...props.bitmap.thresholds]
  next[i] = clamped
  props.bitmap.thresholds = next.sort((a, b) => a - b)
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('convert.segmentation') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-2 border-t border-slate-700 p-3 text-xs">
      <p v-if="isDocument" class="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[11px] leading-snug text-slate-400">
        {{ t('convert.embeddedImageHint') }}
      </p>

      <div class="space-y-1">
        <p class="text-slate-400">{{ t('convert.segmentationMethod') }}</p>
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="method in SEG_METHODS"
            :key="method"
            type="button"
            class="rounded border px-2 py-1.5 text-left text-[11px] transition"
            :class="bitmap.segmentation_method === method
              ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
              : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
            :title="t(`convert.seg_${method}_hint`)"
            @click="bitmap.segmentation_method = method"
          >
            <span class="block font-medium">{{ t(`convert.seg_${method}`) }}</span>
            <span class="block text-[9px] text-slate-500">{{ t(`convert.seg_${method}_hint`) }}</span>
          </button>
        </div>
      </div>

      <!-- Image detail: promoted out of the post-process accordion
           because operators reach for "more detail" often. Higher
           re-segments at a larger source canvas → more fine features
           survive into the SVG, slower preview. Same 4 named tiers as
           MonochromeCard so the vocabulary is consistent across
           print modes. -->
      <div class="space-y-1">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.detail') }}</p>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="level in detailLevels"
            :key="level.id"
            type="button"
            class="rounded border px-2 py-1.5 text-[11px] transition"
            :class="currentDetail === level.id
              ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
              : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
            @click="bitmap.max_dimension_px = level.value"
          >
            {{ t(level.labelKey) }}
          </button>
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.detailHint') }}</p>
      </div>

      <label v-if="bitmap.segmentation_method === 'kmeans'" class="block text-slate-400">
        {{ t('convert.numColors') }}
        <input v-model.number="bitmap.num_colors" type="number" min="1" max="32" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
      </label>

      <label v-else-if="bitmap.segmentation_method === 'luminance_bands'" class="block text-slate-400">
        {{ t('convert.numBands') }}
        <input v-model.number="bitmap.num_bands" type="number" min="2" max="16" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
      </label>

      <div v-else-if="bitmap.segmentation_method === 'thresholds'" class="space-y-1">
        <div class="flex items-center justify-between">
          <span class="text-slate-400">{{ t('convert.thresholds') }}</span>
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
            @click="addThreshold"
          >
            + {{ t('convert.addThreshold') }}
          </button>
        </div>
        <div v-for="(value, i) in bitmap.thresholds" :key="i" class="flex items-center gap-1">
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            :value="value"
            class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            @change="(e) => updateThreshold(i, Number((e.target as HTMLInputElement).value))"
          />
          <button
            type="button"
            class="rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
            @click="removeThreshold(i)"
          >
            ✕
          </button>
        </div>
        <p class="text-[10px] text-slate-500">{{ t('convert.thresholdsHint') }}</p>
      </div>

      <p v-else-if="bitmap.segmentation_method === 'fixed_palette'" class="text-[10px] text-slate-500">
        {{ t('convert.fixedPaletteRefHint') }}
      </p>

      <div class="border-t border-slate-700 pt-2 space-y-2">
        <p class="text-[10px] uppercase tracking-wider text-slate-500">{{ t('convert.postProcess') }}</p>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-slate-400">
            {{ t('convert.minRegion') }}
            <input v-model.number="bitmap.min_region_pixels" type="number" min="0" max="1000" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
          <label class="block text-slate-400">
            {{ t('convert.mergeDeltaE') }}
            <input v-model.number="bitmap.merge_delta_e" type="number" min="0" max="50" step="0.5" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <label class="flex items-center gap-2 self-end text-slate-400">
            <input v-model="bitmap.drop_background" type="checkbox" class="rounded border-slate-600 bg-slate-900" />
            {{ t('convert.dropBackground') }}
          </label>
          <label class="block text-slate-400">{{ t('convert.bgLuminance') }}
            <input v-model.number="bitmap.background_luminance" type="number" min="0" max="1" step="0.01" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
          </label>
        </div>
        <!-- max_dimension_px now lives at the top of the card as a
             named-tier detail picker; no need to duplicate the raw
             numeric input here. -->
      </div>
    </div>
  </div>
</template>
