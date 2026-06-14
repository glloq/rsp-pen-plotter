<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import CollapsibleCard from '../shared/CollapsibleCard.vue'

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

// Defaults mirror defaultBitmap() in useBitmapDraft.
const isDefault = computed(
  () =>
    props.bitmap.min_region_pixels === 0 &&
    props.bitmap.merge_delta_e === 0 &&
    props.bitmap.drop_background === true &&
    props.bitmap.background_luminance === 0.92,
)

function reset(): void {
  props.bitmap.min_region_pixels = 0
  props.bitmap.merge_delta_e = 0
  props.bitmap.drop_background = true
  props.bitmap.background_luminance = 0.92
  draft.markSegmentationTouched('background_luminance')
}
</script>

<template>
  <CollapsibleCard
    card-key="postprocess"
    :title="t('convert.postProcess')"
    resettable
    :can-reset="!isDefault"
    :reset-label="t('preprocess.reset')"
    @reset="reset"
  >
    <div class="grid grid-cols-2 gap-x-2 gap-y-3">
      <label class="block text-slate-400">
        {{ t('convert.minRegion') }}
        <input
          v-model.number="bitmap.min_region_pixels"
          type="number"
          min="0"
          max="5000"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
        <span class="mt-0.5 block text-[10px] leading-snug text-slate-500">{{
          t('convert.minRegionHint')
        }}</span>
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
        <span class="mt-0.5 block text-[10px] leading-snug text-slate-500">{{
          t('convert.mergeDeltaEHint')
        }}</span>
      </label>
    </div>
    <div class="grid grid-cols-2 gap-x-2 gap-y-3">
      <label class="flex items-center gap-2 self-start pt-0.5 text-slate-400">
        <input
          v-model="bitmap.drop_background"
          type="checkbox"
          class="rounded border-slate-600 bg-slate-900 accent-emerald-500"
        />
        {{ t('convert.dropBackground') }}
      </label>
      <label class="block text-slate-400"
        >{{ t('convert.bgLuminance') }}
        <span class="font-mono text-[10px] text-slate-500">(0–1)</span>
        <input
          :value="bitmap.background_luminance"
          type="number"
          min="0"
          max="1"
          step="0.01"
          :disabled="!bitmap.drop_background"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          @input="onBgLuminanceInput"
        />
        <span class="mt-0.5 block text-[10px] leading-snug text-slate-500">{{
          t('convert.bgLuminanceHint')
        }}</span>
      </label>
    </div>
  </CollapsibleCard>
</template>
