<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'

// Brightness / contrast / saturation / gamma — the day-to-day knobs.
// Every slider is bound directly to the singleton draft via the
// ``preprocess`` prop (passed by reference); the modal's preview
// scheduler picks up changes via its deep watcher and reschedules
// /preview on each release.

defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()
const expanded = useAccordionPersistence('preprocess.basic', true)
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('preprocess.basic.title') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-3 border-t border-slate-700 p-3 text-xs">
      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.basic.brightness') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{
            preprocess.brightness.toFixed(2)
          }}</span>
        </div>
        <input
          v-model.number="preprocess.brightness"
          type="range"
          min="-1"
          max="1"
          step="0.01"
          class="mt-1 w-full"
        />
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.basic.contrast') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{
            preprocess.contrast.toFixed(2)
          }}</span>
        </div>
        <input
          v-model.number="preprocess.contrast"
          type="range"
          min="-1"
          max="1"
          step="0.01"
          class="mt-1 w-full"
        />
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.basic.saturation') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{
            preprocess.saturation.toFixed(2)
          }}</span>
        </div>
        <input
          v-model.number="preprocess.saturation"
          type="range"
          min="0"
          max="2"
          step="0.01"
          class="mt-1 w-full"
        />
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.basic.gamma') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{
            preprocess.gamma.toFixed(2)
          }}</span>
        </div>
        <input
          v-model.number="preprocess.gamma"
          type="range"
          min="0.2"
          max="3"
          step="0.05"
          class="mt-1 w-full"
        />
        <p class="mt-1 text-[10px] text-slate-500">{{ t('preprocess.basic.gammaHint') }}</p>
      </label>
    </div>
  </div>
</template>
