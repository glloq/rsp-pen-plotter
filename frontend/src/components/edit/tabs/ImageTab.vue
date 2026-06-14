<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  defaultPreprocess,
  isPreprocessNeutral,
  useBitmapDraft,
} from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import BasicAdjustmentsCard from '../image/BasicAdjustmentsCard.vue'
import LevelsCard from '../image/LevelsCard.vue'
import FiltersCard from '../image/FiltersCard.vue'
import TransformCard from '../image/TransformCard.vue'
import TabEmptyState from '../shared/TabEmptyState.vue'

// Image tab — photo-editor adjustments (brightness, contrast,
// saturation, gamma, levels, sharpen/blur, invert, grayscale, rotate,
// flip, crop) applied to the loaded RGB image *before* the downscale
// and segmentation pass. The single source of truth is
// ``draft.bitmap.value.preprocess``; the four cards below read/write
// it directly. The Reset button hands the operator a one-click
// rollback to neutral so they can compare with the unmodified source.

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)

const preprocess = computed(() => draft.bitmap.value.preprocess)
const neutral = computed(() => isPreprocessNeutral(preprocess.value))

function resetPreprocess(): void {
  draft.bitmap.value.preprocess = defaultPreprocess()
}
</script>

<template>
  <section v-if="fm.hasSource.value && fm.showsBitmapForm.value" class="space-y-3">
    <div
      class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-[11px] text-slate-400"
    >
      <div class="flex items-center justify-between">
        <span>{{ t('preprocess.intro') }}</span>
        <button
          type="button"
          :disabled="neutral"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300 transition hover:border-emerald-700 hover:text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-700 disabled:hover:text-slate-300"
          @click="resetPreprocess"
        >
          {{ t('preprocess.reset') }}
        </button>
      </div>
      <p class="text-[10px] leading-snug text-slate-500">
        {{ t('preprocess.previewNote') }}
      </p>
    </div>

    <BasicAdjustmentsCard :preprocess="preprocess" />
    <LevelsCard :preprocess="preprocess" />
    <FiltersCard :preprocess="preprocess" />
    <TransformCard :preprocess="preprocess" />
  </section>

  <TabEmptyState v-else-if="!fm.hasSource.value" :message="t('preprocess.noSource')" />

  <TabEmptyState v-else :message="t('preprocess.notApplicable')" />
</template>
