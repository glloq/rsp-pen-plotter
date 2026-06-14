<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'
import CollapsibleCard from '../shared/CollapsibleCard.vue'
import LabeledSlider from '../shared/LabeledSlider.vue'

// Black/white points + the optional auto-contrast stretch. Particularly
// useful before the ``thresholds`` segmentation mode: an operator can
// recentre the dynamic range so the threshold ends up where they want
// it rather than chasing a moving target with the threshold sliders.

const props = defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()

// Keep black < white (with at least 1 unit of headroom) so the
// backend's clamping doesn't silently invert the levels behind the
// operator's back. Mutating in the input handler instead of a watcher
// keeps both edges responsive even when the user drags the sliders
// past each other.
function onBlackChange(value: number): void {
  const next = Math.min(254, Math.max(0, Math.round(value)))
  props.preprocess.black_point = next
  if (props.preprocess.white_point <= next) {
    props.preprocess.white_point = Math.min(255, next + 1)
  }
}

function onWhiteChange(value: number): void {
  const next = Math.min(255, Math.max(1, Math.round(value)))
  props.preprocess.white_point = next
  if (props.preprocess.black_point >= next) {
    props.preprocess.black_point = Math.max(0, next - 1)
  }
}

const isNeutral = computed(
  () =>
    props.preprocess.black_point === 0 &&
    props.preprocess.white_point === 255 &&
    !props.preprocess.auto_contrast,
)

function reset(): void {
  props.preprocess.black_point = 0
  props.preprocess.white_point = 255
  props.preprocess.auto_contrast = false
}
</script>

<template>
  <CollapsibleCard
    card-key="preprocess.levels"
    :title="t('preprocess.levels.title')"
    resettable
    :can-reset="!isNeutral"
    :reset-label="t('preprocess.reset')"
    @reset="reset"
  >
    <LabeledSlider
      :model-value="preprocess.black_point"
      :label="t('preprocess.levels.black')"
      :min="0"
      :max="254"
      :step="1"
      @update:model-value="onBlackChange"
    />
    <LabeledSlider
      :model-value="preprocess.white_point"
      :label="t('preprocess.levels.white')"
      :min="1"
      :max="255"
      :step="1"
      @update:model-value="onWhiteChange"
    />
    <label class="flex items-center gap-2 text-slate-300">
      <input v-model="preprocess.auto_contrast" type="checkbox" class="accent-emerald-500" />
      <span>{{ t('preprocess.levels.auto') }}</span>
    </label>
    <p class="text-[10px] text-slate-500">{{ t('preprocess.levels.hint') }}</p>
  </CollapsibleCard>
</template>
