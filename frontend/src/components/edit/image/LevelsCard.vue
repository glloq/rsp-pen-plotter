<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'

// Black/white points + the optional auto-contrast stretch. Particularly
// useful before the ``thresholds`` segmentation mode: an operator can
// recentre the dynamic range so the threshold ends up where they want
// it rather than chasing a moving target with the threshold sliders.

const props = defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()
const expanded = useAccordionPersistence('preprocess.levels', false)

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
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('preprocess.levels.title') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-3 border-t border-slate-700 p-3 text-xs">
      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.levels.black') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{ preprocess.black_point }}</span>
        </div>
        <input
          :value="preprocess.black_point"
          type="range"
          min="0"
          max="254"
          step="1"
          class="mt-1 w-full"
          @input="onBlackChange(($event.target as HTMLInputElement).valueAsNumber)"
        />
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.levels.white') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{ preprocess.white_point }}</span>
        </div>
        <input
          :value="preprocess.white_point"
          type="range"
          min="1"
          max="255"
          step="1"
          class="mt-1 w-full"
          @input="onWhiteChange(($event.target as HTMLInputElement).valueAsNumber)"
        />
      </label>

      <label class="flex items-center gap-2 text-slate-300">
        <input v-model="preprocess.auto_contrast" type="checkbox" class="accent-emerald-500" />
        <span>{{ t('preprocess.levels.auto') }}</span>
      </label>
      <p class="text-[10px] text-slate-500">{{ t('preprocess.levels.hint') }}</p>
    </div>
  </div>
</template>
