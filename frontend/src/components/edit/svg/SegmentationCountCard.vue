<script setup lang="ts">
// Layer / colour count — the headline knob of the SVG tab, surfaced at the
// very top because it drives BOTH the detail granularity AND how many distinct
// inks get pulled from the palette: each layer is one cluster, snapped to its
// nearest available ink. The control adapts to the active segmentation method
// (colours for kmeans / palette methods, tonal bands for luminance, cut points
// for thresholds). Lives outside the (collapsible) method card so it stays
// visible.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SegmentationMethod } from '../../../api/client'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { resolveEffectivePalette } from '../../../lib/effectivePalette'
import { nextPadColor } from '../../../lib/paletteColors'
import { useAvailableColorsStore } from '../../../stores/availableColors'
import { useJobStore } from '../../../stores/job'
import { usePaletteSourceStore } from '../../../stores/paletteSource'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

interface BitmapDraft {
  segmentation_method: SegmentationMethod
  num_colors: number
  num_bands: number
  thresholds: number[]
  palette: string[]
  [key: string]: unknown
}

const props = defineProps<{ bitmap: BitmapDraft }>()

const { t } = useI18n()
const draft = useBitmapDraft()
const job = useJobStore()
const paletteSource = usePaletteSourceStore()
const availableColors = useAvailableColorsStore()

const isKmeans = computed(
  () =>
    props.bitmap.segmentation_method === 'kmeans' ||
    props.bitmap.segmentation_method === 'kmeans_lab',
)
const isBands = computed(() => props.bitmap.segmentation_method === 'luminance_bands')
const isThresholds = computed(() => props.bitmap.segmentation_method === 'thresholds')
const isPalette = computed(
  () =>
    props.bitmap.segmentation_method === 'fixed_palette' ||
    props.bitmap.segmentation_method === 'palette_dither',
)
// kmeans, kmeans_lab AND the palette-driven methods all count by colour, so
// they share the same num_colors slider.
const usesColourCount = computed(() => isKmeans.value || isPalette.value)

// Pool a manual-palette resize pads from (machine pens / inventory / union).
const effectivePool = computed<string[]>(() => {
  const pens = (job.selectedProfile?.pens ?? [])
    .filter((p) => p.installed && p.color)
    .map((p) => p.color)
  const available = availableColors.ordered.map((c) => c.hex)
  return resolveEffectivePalette(paletteSource.source, pens, available)
})

// Colour count — clamp to the practical 1..16 range the backend caps k at.
// For a MANUAL fixed_palette / palette_dither (the operator hand-picked the
// inks, not following the pens), keep the palette length in lock-step so the
// count is actually honoured — palette methods count by palette length. An
// empty palette downgrades to kmeans + num_colors on the wire, so leave it be.
function setNumColors(value: number): void {
  const target = Math.max(1, Math.min(16, Math.round(value) || 1))
  props.bitmap.num_colors = target
  if (isPalette.value && props.bitmap.palette.length > 0 && !draft.paletteFollowsPens.value) {
    const current = props.bitmap.palette
    if (current.length > target) {
      props.bitmap.palette = current.slice(0, target)
    } else if (current.length < target) {
      const used = new Set(current.map((h) => h.toLowerCase()))
      const unusedPool = effectivePool.value.filter((h) => !used.has(h.toLowerCase()))
      const padded = [...current]
      while (padded.length < target) {
        padded.push(unusedPool.shift() ?? nextPadColor(padded))
      }
      props.bitmap.palette = padded
    }
  }
}

function setNumBands(value: number): void {
  props.bitmap.num_bands = value
  draft.markSegmentationTouched('num_bands')
}

function addThreshold(): void {
  props.bitmap.thresholds = [...props.bitmap.thresholds, 0.5].sort((a, b) => a - b)
  draft.markSegmentationTouched('thresholds')
}
function removeThreshold(i: number): void {
  props.bitmap.thresholds = props.bitmap.thresholds.filter((_, idx) => idx !== i)
  draft.markSegmentationTouched('thresholds')
}
function updateThreshold(i: number, value: number): void {
  // Clamp in place WITHOUT sorting: the rows are index-keyed and the edited
  // input is still focused, so re-sorting here would yank focus mid-edit. The
  // list is re-ordered on blur (commitThresholdOrder).
  const clamped = Math.max(0, Math.min(1, value))
  const next = [...props.bitmap.thresholds]
  next[i] = clamped
  props.bitmap.thresholds = next
  draft.markSegmentationTouched('thresholds')
}
function commitThresholdOrder(): void {
  const sorted = [...props.bitmap.thresholds].sort((a, b) => a - b)
  if (sorted.some((v, idx) => v !== props.bitmap.thresholds[idx])) {
    props.bitmap.thresholds = sorted
  }
}
</script>

<template>
  <div class="card space-y-2 text-xs" data-test="svg-layer-count">
    <div class="flex items-center justify-between">
      <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-300">
        {{ t('svg.layerCountTitle') }}
      </p>
      <LayerCountBadge :count="draft.expectedLayerCount.value" />
    </div>

    <!-- kmeans / kmeans_lab / fixed_palette / palette_dither → colour count
         (slider + number, 1..16). -->
    <template v-if="usesColourCount">
      <div class="flex items-center gap-2">
        <input
          :value="bitmap.num_colors"
          type="range"
          :min="1"
          :max="16"
          step="1"
          class="w-full accent-emerald-500"
          data-test="svg-num-colors-range"
          @input="(e) => setNumColors(Number((e.target as HTMLInputElement).value))"
        />
        <input
          :value="bitmap.num_colors"
          type="number"
          :min="1"
          :max="16"
          step="1"
          class="w-14 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-100"
          data-test="svg-num-colors-input"
          @change="(e) => setNumColors(Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <!-- Palette methods draw with a SPECIFIC ink list; the slider sets how
           many, the exact colours are edited on the Style tab. -->
      <p v-if="isPalette" class="text-[10px] text-slate-500">
        {{ t('convert.fixedPaletteRefHint') }}
      </p>
    </template>

    <!-- luminance_bands → tonal band count. -->
    <template v-else-if="isBands">
      <input
        :value="bitmap.num_bands"
        type="number"
        :min="2"
        :max="16"
        class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        data-test="svg-num-bands-input"
        @input="(e) => setNumBands(Number((e.target as HTMLInputElement).value))"
      />
    </template>

    <!-- thresholds → editable cut-point list. -->
    <template v-else-if="isThresholds">
      <div class="flex items-center justify-between">
        <span class="text-slate-400">{{ t('convert.thresholds') }}</span>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
          @click="addThreshold"
        >
          + {{ t('convert.addThreshold') }}
        </button>
      </div>
      <div v-for="(value, i) in bitmap.thresholds" :key="i" class="flex items-center gap-1">
        <input
          type="number"
          min="0"
          max="1"
          step="0.01"
          :value="value"
          class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          @change="(e) => updateThreshold(i, Number((e.target as HTMLInputElement).value))"
          @blur="commitThresholdOrder"
        />
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
          @click="removeThreshold(i)"
        >
          ✕
        </button>
      </div>
      <p class="text-[10px] text-slate-500">{{ t('convert.thresholdsHint') }}</p>
    </template>

    <p class="text-[10px] leading-snug text-slate-500">{{ t('svg.layerCountHint') }}</p>
  </div>
</template>
