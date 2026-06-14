<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'
import CollapsibleCard from '../shared/CollapsibleCard.vue'
import LabeledSlider from '../shared/LabeledSlider.vue'

// Brightness / contrast / saturation / gamma — the day-to-day knobs.
// Every slider is bound directly to the singleton draft via the
// ``preprocess`` prop (passed by reference); the modal's preview
// scheduler picks up changes via its deep watcher and reschedules
// /preview on each release. Each slider also exposes a numeric input
// (via LabeledSlider) so an exact value can be typed.

const props = defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()

// Neutral values mirror defaultPreprocess() — the per-section reset
// rolls just these four fields back without touching levels/filters.
const isNeutral = computed(
  () =>
    props.preprocess.brightness === 0 &&
    props.preprocess.contrast === 0 &&
    props.preprocess.saturation === 1 &&
    props.preprocess.gamma === 1,
)

function reset(): void {
  props.preprocess.brightness = 0
  props.preprocess.contrast = 0
  props.preprocess.saturation = 1
  props.preprocess.gamma = 1
}
</script>

<template>
  <CollapsibleCard
    card-key="preprocess.basic"
    :title="t('preprocess.basic.title')"
    :default-expanded="true"
    resettable
    :can-reset="!isNeutral"
    :reset-label="t('preprocess.reset')"
    @reset="reset"
  >
    <LabeledSlider
      :model-value="preprocess.brightness"
      :label="t('preprocess.basic.brightness')"
      :min="-1"
      :max="1"
      :step="0.01"
      @update:model-value="(v) => (preprocess.brightness = v)"
    />
    <LabeledSlider
      :model-value="preprocess.contrast"
      :label="t('preprocess.basic.contrast')"
      :min="-1"
      :max="1"
      :step="0.01"
      @update:model-value="(v) => (preprocess.contrast = v)"
    />
    <LabeledSlider
      :model-value="preprocess.saturation"
      :label="t('preprocess.basic.saturation')"
      :min="0"
      :max="2"
      :step="0.01"
      @update:model-value="(v) => (preprocess.saturation = v)"
    />
    <LabeledSlider
      :model-value="preprocess.gamma"
      :label="t('preprocess.basic.gamma')"
      :min="0.2"
      :max="3"
      :step="0.05"
      :hint="t('preprocess.basic.gammaHint')"
      @update:model-value="(v) => (preprocess.gamma = v)"
    />
  </CollapsibleCard>
</template>
