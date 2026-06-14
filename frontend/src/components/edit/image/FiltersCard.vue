<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'
import CollapsibleCard from '../shared/CollapsibleCard.vue'
import LabeledSlider from '../shared/LabeledSlider.vue'

// Sharpen / blur and the two colour toggles (invert, grayscale).
// Sharpen and blur are mutually useful — a touch of blur first kills
// JPEG noise that would otherwise become spurious clusters in the
// k-means pass; a touch of sharpen afterwards crisps up the edges
// before vectorisation.

const props = defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()

function ditherLabel(v: number): string {
  return v === 0
    ? t('preprocess.filters.ditherOff')
    : `${v} ${t('preprocess.filters.ditherLevels')}`
}

const isNeutral = computed(
  () =>
    props.preprocess.sharpen === 0 &&
    props.preprocess.blur_px === 0 &&
    !props.preprocess.invert &&
    !props.preprocess.grayscale &&
    props.preprocess.dither_levels === 0,
)

function reset(): void {
  props.preprocess.sharpen = 0
  props.preprocess.blur_px = 0
  props.preprocess.invert = false
  props.preprocess.grayscale = false
  props.preprocess.dither_levels = 0
}
</script>

<template>
  <CollapsibleCard
    card-key="preprocess.filters"
    :title="t('preprocess.filters.title')"
    resettable
    :can-reset="!isNeutral"
    :reset-label="t('preprocess.reset')"
    @reset="reset"
  >
    <LabeledSlider
      :model-value="preprocess.sharpen"
      :label="t('preprocess.filters.sharpen')"
      :min="0"
      :max="2"
      :step="0.05"
      @update:model-value="(v) => (preprocess.sharpen = v)"
    />
    <LabeledSlider
      :model-value="preprocess.blur_px"
      :label="t('preprocess.filters.blur')"
      :min="0"
      :max="5"
      :step="0.1"
      unit="px"
      @update:model-value="(v) => (preprocess.blur_px = v)"
    />

    <label class="flex items-center gap-2 text-slate-300">
      <input v-model="preprocess.invert" type="checkbox" class="accent-emerald-500" />
      <span>{{ t('preprocess.filters.invert') }}</span>
    </label>

    <label class="flex items-center gap-2 text-slate-300">
      <input v-model="preprocess.grayscale" type="checkbox" class="accent-emerald-500" />
      <span>{{ t('preprocess.filters.grayscale') }}</span>
    </label>

    <LabeledSlider
      :model-value="preprocess.dither_levels"
      :label="t('preprocess.filters.dither')"
      :min="0"
      :max="8"
      :step="1"
      :numeric="false"
      :format-value="ditherLabel"
      :hint="t('preprocess.filters.ditherHint')"
      @update:model-value="(v) => (preprocess.dither_levels = v)"
    />
  </CollapsibleCard>
</template>
