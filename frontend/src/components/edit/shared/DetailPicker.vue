<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { DETAIL_LEVELS, tierFor, type DetailId } from '../../../composables/useDetailPicker'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useEditState } from '../../../composables/useEditState'
import { usePreviewCostEstimator } from '../../../composables/usePreviewCostEstimator'

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
const draft = useBitmapDraft()
const edit = useEditState()
const costEstimator = usePreviewCostEstimator()

const currentDetail = (): DetailId => tierFor(props.modelValue)

function selectLevel(value: number): void {
  emit('update:modelValue', value)
}

// Per-tier time estimate: take the algorithm/quality the operator is
// currently on, look up the EMA from /preview, and extrapolate to each
// tier's resolution. Cost scales roughly with pixel count (∝ side²)
// because segmentation + render are both per-pixel work; not exact for
// every algorithm but accurate enough to keep the operator from
// blindly clicking Ultra. Returns "" until enough samples exist so the
// chip stays clean on first contact.
function tierEstimateMs(tierValue: number): number {
  const ms = costEstimator.estimateMs(draft.bitmap.value.algorithm, edit.previewQuality.value)
  const current = Math.max(1, props.modelValue)
  const ratio = (tierValue / current) ** 2
  return ms * ratio
}
function formatEstimate(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return ''
  if (ms < 1000) return `~${Math.round(ms / 10) * 10} ms`
  return `~${(ms / 1000).toFixed(ms < 5000 ? 1 : 0)} s`
}
// Tint hint: slow tiers (> 3 s) get an amber-tinted estimate so the
// operator notices before clicking. < 800 ms reads as "fine".
function estimateClass(ms: number): string {
  if (ms >= 3000) return 'text-amber-400'
  if (ms >= 800) return 'text-slate-400'
  return 'text-emerald-400'
}

const tierEstimates = computed(() =>
  DETAIL_LEVELS.map((l) => {
    const ms = tierEstimateMs(l.value)
    return { id: l.id, ms, label: formatEstimate(ms), klass: estimateClass(ms) }
  }),
)
</script>

<template>
  <div class="space-y-1">
    <p v-if="showLabel !== false" class="text-[10px] uppercase tracking-wider text-slate-400">
      {{ t('mono.detail') }}
    </p>
    <div class="grid grid-cols-5 gap-1">
      <button
        v-for="(level, i) in DETAIL_LEVELS"
        :key="level.id"
        type="button"
        class="flex flex-col items-center rounded border px-2 py-1.5 text-[11px] leading-tight transition"
        :class="
          currentDetail() === level.id
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
        "
        @click="selectLevel(level.value)"
      >
        <span>{{ t(level.labelKey) }}</span>
        <span class="text-[9px] font-mono opacity-70">{{ level.value }}px</span>
        <span
          v-if="tierEstimates[i]?.label"
          class="text-[9px] font-mono"
          :class="tierEstimates[i]?.klass"
          >{{ tierEstimates[i]?.label }}</span
        >
      </button>
    </div>
    <p class="text-[10px] text-slate-500">{{ hint ?? t('mono.detailHint') }}</p>
  </div>
</template>
