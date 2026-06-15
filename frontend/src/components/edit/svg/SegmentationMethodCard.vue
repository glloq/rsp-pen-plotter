<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SegmentationMethod } from '../../../api/client'
import CollapsibleCard from '../shared/CollapsibleCard.vue'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'

// Segmentation method picker — HOW the source raster gets sliced into
// per-colour masks before any algorithm renders them. The layer/colour COUNT
// (num_colors / num_bands / thresholds) is the headline knob and lives in the
// sibling ``SegmentationCountCard`` at the very top of the SVG tab; the
// post-processing knobs (drop_background, min_region, merge_delta_e) live on
// the Style tab. This card stays focused on the method choice itself.

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

      <p v-if="bitmap.segmentation_method === 'palette_dither'" class="text-[10px] text-slate-500">
        {{ t('convert.paletteDitherNote') }}
      </p>
    </div>
  </CollapsibleCard>
</template>
