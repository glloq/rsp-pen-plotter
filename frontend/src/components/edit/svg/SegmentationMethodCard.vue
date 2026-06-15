<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SegmentationMethod } from '../../../api/client'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import CollapsibleCard from '../shared/CollapsibleCard.vue'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { kdiag } from '../../../lib/kdiag'

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

const SEG_METHODS: SegmentationMethod[] = [
  'kmeans',
  'kmeans_lab',
  'luminance_bands',
  'thresholds',
  'fixed_palette',
  'palette_dither',
]

// User-driven mutators flag the corresponding field as "touched" so the
// next master-style switch / print-mode flip can warn before stomping.
function selectMethod(method: SegmentationMethod): void {
  kdiag(`selectMethod(${method}) clicked`)
  props.bitmap.segmentation_method = method
  draft.markSegmentationTouched('method')
  // kmeans / kmeans_lab cluster the image's OWN colours — that is the
  // "auto" palette source, which is mutually exclusive with following the
  // pen rack. Turn palette-follows-pens off here so the Style tab's
  // immediate watcher (which otherwise snaps the palette onto the pens
  // and flips the method back to fixed_palette on tab entry) leaves the
  // operator's choice alone. Clearing the palette keeps the Palettecard
  // on its "auto" source instead of falling through to "manual".
  if (method === 'kmeans' || method === 'kmeans_lab') {
    draft.paletteFollowsPens.value = false
    props.bitmap.palette = []
  }
}
function setNumBands(value: number): void {
  props.bitmap.num_bands = value
  draft.markSegmentationTouched('num_bands')
}
function addThreshold(): void {
  props.bitmap.thresholds = [...props.bitmap.thresholds, 0.5].sort((a, b) => a - b)
  draft.markSegmentationTouched('thresholds')
}
function removeThreshold(i: number): void {
  props.bitmap.thresholds = props.bitmap.thresholds.filter((_, idx) => idx !== i)
  draft.markSegmentationTouched('thresholds')
}
function updateThreshold(i: number, value: number): void {
  // Write the clamped value in place WITHOUT sorting: the rows are
  // index-keyed and the edited input is still focused, so re-sorting
  // here would yank the row (and focus) out from under the operator
  // mid-edit. The list is re-ordered on blur (commitThresholdOrder).
  const clamped = Math.max(0, Math.min(1, value))
  const next = [...props.bitmap.thresholds]
  next[i] = clamped
  props.bitmap.thresholds = next
  draft.markSegmentationTouched('thresholds')
}
function commitThresholdOrder(): void {
  const sorted = [...props.bitmap.thresholds].sort((a, b) => a - b)
  // Only patch when the order actually changes — avoids a useless
  // reactive write (and preview reschedule) on every blur.
  if (sorted.some((v, idx) => v !== props.bitmap.thresholds[idx])) {
    props.bitmap.thresholds = sorted
  }
}
</script>

<template>
  <CollapsibleCard
    card-key="segmentation"
    :title="t('convert.segmentation')"
    :default-expanded="true"
  >
    <div class="space-y-2">
      <p
        v-if="isDocument"
        class="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[11px] leading-snug text-slate-400"
      >
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
            :class="
              bitmap.segmentation_method === method
                ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
            "
            :title="t(`convert.seg_${method}_hint`)"
            @click="selectMethod(method)"
          >
            <span class="block font-medium">{{ t(`convert.seg_${method}`) }}</span>
            <span class="block text-[9px] text-slate-500">{{
              t(`convert.seg_${method}_hint`)
            }}</span>
          </button>
        </div>
      </div>

      <label
        v-if="
          bitmap.segmentation_method === 'kmeans' || bitmap.segmentation_method === 'kmeans_lab'
        "
        class="block text-slate-400"
      >
        <span class="inline-flex items-center">
          {{ t('convert.numColors') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </span>
        <input
          v-model.number="bitmap.num_colors"
          type="number"
          min="1"
          max="32"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>

      <label
        v-else-if="bitmap.segmentation_method === 'luminance_bands'"
        class="block text-slate-400"
      >
        <span class="inline-flex items-center">
          {{ t('convert.numBands') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </span>
        <input
          :value="bitmap.num_bands"
          type="number"
          min="2"
          max="16"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          @input="(e) => setNumBands(Number((e.target as HTMLInputElement).value))"
        />
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
            @blur="commitThresholdOrder"
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

      <p
        v-else-if="
          bitmap.segmentation_method === 'fixed_palette' ||
          bitmap.segmentation_method === 'palette_dither'
        "
        class="text-[10px] text-slate-500"
      >
        {{ t('convert.fixedPaletteRefHint') }}
      </p>
      <p v-if="bitmap.segmentation_method === 'palette_dither'" class="text-[10px] text-slate-500">
        {{ t('convert.paletteDitherNote') }}
      </p>
    </div>
  </CollapsibleCard>
</template>
