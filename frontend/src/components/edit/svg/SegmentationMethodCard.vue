<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SegmentationMethod } from '../../../api/client'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'

// Segmentation method picker + the primary parameter for the chosen
// method (num_colors / num_bands / thresholds list / palette ref hint).
// Lives in the SVG tab because the segmentation method is a technical
// vectorisation decision: it controls how the source raster gets sliced
// into per-colour masks before any algorithm renders them. The
// post-processing knobs (drop_background, min_region, merge_delta_e)
// live in a sibling card on the Style tab — they filter what the
// segmentation produces and are more naturally a colour-/output-shaping
// concern than a segmentation choice.

interface BitmapDraft {
  segmentation_method: SegmentationMethod
  num_colors: number
  num_bands: number
  thresholds: number[]
  palette: string[]
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
const draft = useBitmapDraft()

const expanded = useAccordionPersistence('segmentation', true)
const SEG_METHODS: SegmentationMethod[] = ['kmeans', 'luminance_bands', 'thresholds', 'fixed_palette']

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

      <label v-if="bitmap.segmentation_method === 'kmeans'" class="block text-slate-400">
        <span class="inline-flex items-center">
          {{ t('convert.numColors') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </span>
        <input v-model.number="bitmap.num_colors" type="number" min="1" max="32" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
      </label>

      <label v-else-if="bitmap.segmentation_method === 'luminance_bands'" class="block text-slate-400">
        <span class="inline-flex items-center">
          {{ t('convert.numBands') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </span>
        <input v-model.number="bitmap.num_bands" type="number" min="1" max="16" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
      </label>

      <div v-else-if="bitmap.segmentation_method === 'thresholds'" class="space-y-1">
        <div class="flex items-center justify-between">
          <span class="inline-flex items-center text-slate-400">
            {{ t('convert.thresholds') }}
            <LayerCountBadge :count="draft.expectedLayerCount.value" />
          </span>
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
    </div>
  </div>
</template>
