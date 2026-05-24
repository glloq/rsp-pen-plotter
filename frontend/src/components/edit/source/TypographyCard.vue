<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useAccordionPersistence } from '../../../composables/useAccordionPersistence'

// Typography card: font + sizing knobs for plain-text and markdown
// sources. Only rendered when the active source is a typography file
// (.txt / .md). The typo reactive object is passed by reference so
// v-model binds straight to its fields and parent watchers fire.

interface TypographyDraft {
  font: string
  font_size_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  margin_mm: number
  page_width_mm: number
  page_height_mm: number
}

defineProps<{
  typo: TypographyDraft
  fonts: string[]
}>()

const { t } = useI18n()

const expanded = useAccordionPersistence('typography', false)
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-3 py-2 text-xs uppercase tracking-wide text-slate-400 hover:text-slate-200"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ t('convert.options') }}
      <span class="text-slate-500">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div v-if="expanded" class="space-y-2 border-t border-slate-700 p-3 text-xs">
      <div class="grid grid-cols-2 gap-2">
        <label class="block text-slate-400">{{ t('convert.font') }}
          <select v-model="typo.font" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
            <option v-for="font in fonts" :key="font" :value="font">{{ font }}</option>
          </select>
        </label>
        <label class="block text-slate-400">{{ t('convert.alignment') }}
          <select v-model="typo.alignment" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100">
            <option value="left">left</option>
            <option value="center">center</option>
            <option value="right">right</option>
          </select>
        </label>
        <label class="block text-slate-400">{{ t('convert.fontSize') }}
          <input v-model.number="typo.font_size_mm" type="number" step="0.5" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
        <label class="block text-slate-400">{{ t('convert.lineSpacing') }}
          <input v-model.number="typo.line_spacing" type="number" step="0.1" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
        <label class="block text-slate-400">{{ t('convert.strokeWidth') }}
          <input v-model.number="typo.stroke_width_mm" type="number" step="0.1" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
        <label class="block text-slate-400">{{ t('convert.margin') }}
          <input v-model.number="typo.margin_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
        <label class="block text-slate-400">{{ t('convert.pageWidth') }}
          <input v-model.number="typo.page_width_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
        <label class="block text-slate-400">{{ t('convert.pageHeight') }}
          <input v-model.number="typo.page_height_mm" type="number" step="any" class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100" />
        </label>
      </div>
    </div>
  </div>
</template>
