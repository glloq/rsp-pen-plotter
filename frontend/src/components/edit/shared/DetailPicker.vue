<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { DETAIL_LEVELS, tierFor, type DetailId } from '../../../composables/useDetailPicker'

// Named-tier picker for ``max_dimension_px`` — the longer side of the
// segmentation canvas. Same component now used by both the Colors and
// Render tabs (and by the legacy MonochromeCard / SegmentationCard
// during the migration), so the tier vocabulary stays consistent
// across the editor and the duplicated tier table + currentDetail
// resolver are gone.

const props = defineProps<{
  modelValue: number
  // Optional hint text rendered under the buttons. Consumers pass the
  // already-translated string so this file doesn't need its own i18n
  // keys; defaults to ``mono.detailHint`` for backward compat with
  // the original MonochromeCard markup.
  hint?: string
  // When false, the section heading is hidden (used by tabs that
  // already group the control under their own header).
  showLabel?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

const { t } = useI18n()

const currentDetail = (): DetailId => tierFor(props.modelValue)

function selectLevel(value: number): void {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="space-y-1">
    <p
      v-if="showLabel !== false"
      class="text-[10px] uppercase tracking-wider text-slate-400"
    >
      {{ t('mono.detail') }}
    </p>
    <div class="grid grid-cols-4 gap-1">
      <button
        v-for="level in DETAIL_LEVELS"
        :key="level.id"
        type="button"
        class="rounded border px-2 py-1.5 text-[11px] transition"
        :class="currentDetail() === level.id
          ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
          : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
        @click="selectLevel(level.value)"
      >
        {{ t(level.labelKey) }}
      </button>
    </div>
    <p class="text-[10px] text-slate-500">{{ hint ?? t('mono.detailHint') }}</p>
  </div>
</template>
