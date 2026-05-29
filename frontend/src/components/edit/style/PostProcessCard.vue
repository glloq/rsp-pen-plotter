<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'

// Post-processing filters applied after segmentation, regardless of
// method: drop near-background pixels, prune small artifact regions
// and merge near-duplicate palette entries. Lives on the Style tab
// because these are output-shaping knobs (what survives into the
// rendered SVG) rather than a vectorisation choice — the segmentation
// method itself sits on the SVG tab.

interface BitmapDraft {
  drop_background: boolean
  background_luminance: number
  min_region_pixels: number
  merge_delta_e: number
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapDraft
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

// Manual edit of the background-drop threshold pins it: mark it touched so
// the band-count auto-tune (setNumBands) stops overriding the operator's
// chosen value.
function onBgLuminanceInput(e: Event): void {
  props.bitmap.background_luminance = Number((e.target as HTMLInputElement).value)
  draft.markSegmentationTouched('background_luminance')
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 text-xs space-y-2">
    <p class="text-[10px] uppercase tracking-wider text-slate-500">
      {{ t('convert.postProcess') }}
    </p>
    <div class="grid grid-cols-2 gap-2">
      <label class="block text-slate-400">
        {{ t('convert.minRegion') }}
        <input
          v-model.number="bitmap.min_region_pixels"
          type="number"
          min="0"
          max="5000"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
      <label class="block text-slate-400">
        {{ t('convert.mergeDeltaE') }}
        <input
          v-model.number="bitmap.merge_delta_e"
          type="number"
          min="0"
          max="50"
          step="0.5"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
    </div>
    <div class="grid grid-cols-2 gap-2">
      <label class="flex items-center gap-2 self-end text-slate-400">
        <input
          v-model="bitmap.drop_background"
          type="checkbox"
          class="rounded border-slate-600 bg-slate-900"
        />
        {{ t('convert.dropBackground') }}
      </label>
      <label class="block text-slate-400"
        >{{ t('convert.bgLuminance') }}
        <input
          :value="bitmap.background_luminance"
          type="number"
          min="0"
          max="1"
          step="0.01"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          @input="onBgLuminanceInput"
        />
      </label>
    </div>
  </div>
</template>
