<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// Output mode picker: multicolor splits the image into N layers (one
// per detected colour), monochrome collapses everything into one ink
// rendered as halftone / stippling. Mode is computed from num_colors
// in the parent so changes elsewhere (kmeans num_colors slider) stay
// in sync — we just surface the two-button toggle here.

defineProps<{
  mode: 'multicolor' | 'monochrome'
}>()

const emit = defineEmits<{
  (e: 'update:mode', value: 'multicolor' | 'monochrome'): void
}>()

const { t } = useI18n()
</script>

<template>
  <div class="card space-y-2 text-xs">
    <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('printMode.title') }}</p>
    <div class="grid grid-cols-2 gap-1">
      <button
        type="button"
        class="rounded border px-2 py-1.5 text-left text-[11px] transition"
        :class="
          mode === 'multicolor'
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        @click="emit('update:mode', 'multicolor')"
      >
        <span class="block font-medium">{{ t('printMode.multicolor') }}</span>
        <span class="block text-[9px] text-slate-500">{{ t('printMode.multicolorHint') }}</span>
      </button>
      <button
        type="button"
        class="rounded border px-2 py-1.5 text-left text-[11px] transition"
        :class="
          mode === 'monochrome'
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        @click="emit('update:mode', 'monochrome')"
      >
        <span class="block font-medium">{{ t('printMode.monochrome') }}</span>
        <span class="block text-[9px] text-slate-500">{{ t('printMode.monochromeHint') }}</span>
      </button>
    </div>
    <p class="text-[10px] leading-snug text-slate-500">{{ t('printMode.modeHint') }}</p>
  </div>
</template>
