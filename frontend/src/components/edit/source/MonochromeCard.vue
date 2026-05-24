<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { MONO_MODES, type MonoMode } from '../../../data/monoModes'
import DetailPicker from '../shared/DetailPicker.vue'
import PenSlotPicker from '../shared/PenSlotPicker.vue'

// Mono-ink rendering card driven by named modes (Pencil, Halftone,
// Stippling, Engraving, Contours, Outline, TSP, Spiral). Each mode is
// a recipe that combines segmentation + per-band algorithm overrides
// — see data/monoModes.ts. The card exposes:
//   - which pen plots every produced layer
//   - which mode to use (8 visual styles)
//   - bands count (only for shaded modes — binary modes ignore it)
//   - binarisation threshold (only for binary modes)
//   - image detail (max_dimension_px tiered as Fast/Standard/High/Ultra)
//
// All other algorithm-specific knobs (angles, density, spacing) are
// owned by the mode recipe and applied per band post-upload via
// /rerender (see SourceSection.applyMonoOverrides).

interface BitmapDraft {
  algorithm: string
  algorithm_options: Record<string, unknown>
  num_bands: number
  thresholds: number[]
  max_dimension_px: number
  drop_background: boolean
  background_luminance: number
  segmentation_method: string
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapDraft
  monoPenSlot: number
  monoModeId: string
}>()

const emit = defineEmits<{
  (e: 'update:monoPenSlot', value: number): void
  (e: 'update:monoModeId', value: string): void
}>()

const { t } = useI18n()

// ============================== PEN SLOT ==============================
// The grid of installed-pen swatches now lives in shared/PenSlotPicker
// so LayerCard and future bulk-assign UIs use the same component.

function setSlot(index: number): void {
  emit('update:monoPenSlot', index)
}

// ============================== MODE PICKER ==============================
// Selecting a mode rewrites the draft's segmentation + uniform
// algorithm (used at /upload). Per-band overrides are applied
// post-upload in SourceSection so they survive a /rerender flush.
const activeMode = computed<MonoMode>(
  () => MONO_MODES.find((m) => m.id === props.monoModeId) ?? MONO_MODES[0]!,
)

function selectMode(mode: MonoMode): void {
  // Apply the mode's segmentation + algorithm choices into the draft;
  // the parent's deep watcher reschedules /preview with the new
  // payload. The numeric knobs (bands count / threshold) keep their
  // current value if it's compatible, otherwise reset to the mode's
  // default — so flipping between Pencil-3 and Halftone-3 doesn't
  // wipe the operator's bands choice.
  props.bitmap.segmentation_method = mode.segmentation_method
  props.bitmap.drop_background = mode.drop_background
  props.bitmap.background_luminance = mode.background_luminance
  props.bitmap.algorithm = mode.default_algorithm
  props.bitmap.algorithm_options = { ...mode.default_algorithm_options }
  if (mode.segmentation_method === 'luminance_bands') {
    if (props.bitmap.num_bands < 2 || props.bitmap.num_bands > 6) {
      props.bitmap.num_bands = mode.default_bands
    }
  } else {
    // Thresholds mode: a single split — defaults to the mode's preferred
    // luminance cutoff. The list shape mirrors what buildSegmentationOptions
    // expects (sorted floats in [0, 1]).
    props.bitmap.thresholds = [mode.default_threshold]
  }
  emit('update:monoModeId', mode.id)
}

// ============================== BANDS / THRESHOLD KNOBS ==============================
// Only one of these is visible at a time, dictated by the active
// mode's segmentation_method.
const usesBands = computed(() => activeMode.value.segmentation_method === 'luminance_bands')

const thresholdValue = computed({
  get: () => props.bitmap.thresholds[0] ?? 0.5,
  set: (v: number) => {
    props.bitmap.thresholds = [Math.max(0, Math.min(1, v))]
  },
})

// ============================== DETAIL LEVEL ==============================
// The Low/Standard/High/Max tier table lives in
// ``composables/useDetailPicker`` now and the render lives in
// ``shared/DetailPicker.vue``. The MonochromeCard just binds
// max_dimension_px through v-model.

const detailValue = computed<number>({
  get: () => props.bitmap.max_dimension_px,
  set: (v: number) => {
    props.bitmap.max_dimension_px = v
  },
})
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
    <!-- Pen slot -->
    <PenSlotPicker
      :model-value="monoPenSlot"
      @update:model-value="setSlot"
    />

    <!-- Mode picker -->
    <div class="space-y-1">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.modeLabel') }}</p>
      <div class="grid grid-cols-2 gap-1">
        <button
          v-for="mode in MONO_MODES"
          :key="mode.id"
          type="button"
          class="flex flex-col gap-0.5 rounded border px-2 py-1.5 text-left text-[11px] transition"
          :class="monoModeId === mode.id
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
          :title="t(mode.descKey)"
          @click="selectMode(mode)"
        >
          <span class="font-medium">{{ t(mode.labelKey) }}</span>
          <span class="text-[9px] text-slate-500">{{ t(mode.descKey) }}</span>
        </button>
      </div>
    </div>

    <!-- Bands count (shaded modes) or threshold (binary modes) -->
    <div v-if="usesBands" class="space-y-1">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.shades') }}</p>
        <span class="font-mono text-[11px] text-slate-300">{{ bitmap.num_bands }}</span>
      </div>
      <input
        v-model.number="bitmap.num_bands"
        type="range"
        min="2"
        max="6"
        step="1"
        class="w-full accent-emerald-500"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.shadesHint') }}</p>
    </div>
    <div v-else class="space-y-1">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.threshold') }}</p>
        <span class="font-mono text-[11px] text-slate-300">{{ thresholdValue.toFixed(2) }}</span>
      </div>
      <input
        v-model.number="thresholdValue"
        type="range"
        min="0.1"
        max="0.9"
        step="0.05"
        class="w-full accent-emerald-500"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.thresholdHint') }}</p>
    </div>

    <!-- Detail level -->
    <DetailPicker v-model="detailValue" />

    <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400">
      {{ t('mono.layersHint') }}
    </p>
  </div>
</template>
