<script setup lang="ts">
// "Nombre de couleurs" (M) — how many DISTINCT inks the print draws, decoupled
// from the layer/detail count (N = ``num_colors``, set on the SVG tab). The N
// segments are quantised onto M inks auto-chosen as the image's M dominant
// colours snapped to the available list; segments sharing an ink merge. Sits at
// the top of the Style tab so the operator sets "how many colours" before
// picking the style that draws them. M is clamped to N — you can't draw more
// colours than there are segments.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

interface BitmapDraft {
  num_colors: number
  color_count: number
  [key: string]: unknown
}

const props = defineProps<{ bitmap: BitmapDraft }>()
const { t } = useI18n()

const maxColors = computed(() => Math.max(1, props.bitmap.num_colors))
const effective = computed(() => Math.max(1, Math.min(props.bitmap.color_count, maxColors.value)))

function setColorCount(value: number): void {
  props.bitmap.color_count = Math.max(1, Math.min(maxColors.value, Math.round(value) || 1))
}
</script>

<template>
  <div class="space-y-1" data-test="style-color-count">
    <div class="flex items-center justify-between">
      <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-300">
        {{ t('style.colorCountTitle') }}
      </p>
      <LayerCountBadge :count="effective" />
    </div>
    <div class="flex items-center gap-2">
      <input
        :value="effective"
        type="range"
        :min="1"
        :max="maxColors"
        step="1"
        class="w-full accent-emerald-500"
        data-test="style-color-count-range"
        @input="(e) => setColorCount(Number((e.target as HTMLInputElement).value))"
      />
      <input
        :value="effective"
        type="number"
        :min="1"
        :max="maxColors"
        step="1"
        class="w-14 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-100"
        data-test="style-color-count-input"
        @change="(e) => setColorCount(Number((e.target as HTMLInputElement).value))"
      />
    </div>
    <p class="text-[10px] leading-snug text-slate-500">{{ t('style.colorCountHint') }}</p>
  </div>
</template>
