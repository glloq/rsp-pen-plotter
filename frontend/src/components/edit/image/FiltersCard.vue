<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'
import type { PreprocessDraft } from '../../../composables/useBitmapDraft'

// Sharpen / blur and the two colour toggles (invert, grayscale).
// Sharpen and blur are mutually useful — a touch of blur first kills
// JPEG noise that would otherwise become spurious clusters in the
// k-means pass; a touch of sharpen afterwards crisps up the edges
// before vectorisation.

defineProps<{ preprocess: PreprocessDraft }>()

const { t } = useI18n()
const expanded = useAccordionPersistence('preprocess.filters', false)
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('preprocess.filters.title') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-3 border-t border-slate-700 p-3 text-xs">
      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.filters.sharpen') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{ preprocess.sharpen.toFixed(2) }}</span>
        </div>
        <input
          v-model.number="preprocess.sharpen"
          type="range"
          min="0"
          max="2"
          step="0.05"
          class="mt-1 w-full"
        />
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.filters.blur') }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{ preprocess.blur_px.toFixed(1) }} px</span>
        </div>
        <input
          v-model.number="preprocess.blur_px"
          type="range"
          min="0"
          max="5"
          step="0.1"
          class="mt-1 w-full"
        />
      </label>

      <label class="flex items-center gap-2 text-slate-300">
        <input v-model="preprocess.invert" type="checkbox" class="accent-emerald-500" />
        <span>{{ t('preprocess.filters.invert') }}</span>
      </label>

      <label class="flex items-center gap-2 text-slate-300">
        <input v-model="preprocess.grayscale" type="checkbox" class="accent-emerald-500" />
        <span>{{ t('preprocess.filters.grayscale') }}</span>
      </label>

      <label class="block text-slate-400">
        <div class="flex items-center justify-between">
          <span>{{ t('preprocess.filters.dither') }}</span>
          <span class="font-mono text-[10px] text-slate-500">
            {{ preprocess.dither_levels === 0
              ? t('preprocess.filters.ditherOff')
              : `${preprocess.dither_levels} ${t('preprocess.filters.ditherLevels')}` }}
          </span>
        </div>
        <input
          v-model.number="preprocess.dither_levels"
          type="range"
          min="0"
          max="8"
          step="1"
          class="mt-1 w-full"
        />
        <p class="mt-1 text-[10px] text-slate-500">{{ t('preprocess.filters.ditherHint') }}</p>
      </label>
    </div>
  </div>
</template>
