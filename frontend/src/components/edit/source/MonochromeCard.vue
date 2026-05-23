<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../../stores/job'
import PrintStylePicker from '../PrintStylePicker.vue'
import AlgoParamsForm from '../AlgoParamsForm.vue'
import type { PrintStyle } from '../../../data/printStyles'

// Mono-ink rendering card. Replaces the broken single-knob mono mode
// that used to ship: ``fixed_palette`` with one colour produced a
// single cluster covering the whole image, which halftone then dot-
// filled uniformly — image content was lost. We now use
// ``luminance_bands`` to split the photograph into N grey shades; all
// shades plot with the same physical pen, but each can carry its own
// render algorithm (configurable per-shade in the Layers tab once
// converted). The card exposes the pre-upload knobs that drive that:
// pen slot, number of shades, image detail, default render style, and
// the style's parameters.

// Lightweight shape — matches the relevant slice of BitmapDraft. The
// card mutates these fields directly via the reactive prop (the
// parent's deep watcher reschedules /preview).
interface BitmapDraft {
  algorithm: string
  num_bands: number
  max_dimension_px: number
  drop_background: boolean
  background_luminance: number
  cell_size_px: number
  density: number
  dot_radius_px: number
  seed: number
  crosshatch_angle_deg: number
  crosshatch_spacing_px: number
  crosshatch_crossed: boolean
  contours_spacing_px: number
  contours_max_rings: number
  edges_stroke_width: number
  spiral_spacing_px: number
  spiral_samples_per_turn: number
  scanlines_spacing_px: number
  scanlines_wave_amp_px: number
  scanlines_wave_period_px: number
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapDraft
  monoPenSlot: number
}>()

const emit = defineEmits<{
  (e: 'update:monoPenSlot', value: number): void
}>()

const { t } = useI18n()
const store = useJobStore()

// ============================== PEN SLOT ==============================
// One pen will plot every shade — the operator picks which slot. The
// post-upload step in SourceSection then assigns ``target_pen_slot``
// on every layer to this value.
const penSlots = computed(() => {
  const profile = store.selectedProfile
  const pens = profile?.pens ?? []
  return Array.from({ length: profile?.pen_slot_count ?? 1 }, (_, i) => {
    const pen = pens.find((p) => p.index === i)
    return {
      index: i,
      name: pen?.name || `${i}`,
      color: pen?.color ?? '#94a3b8',
      installed: pen?.installed ?? false,
    }
  })
})

function setSlot(index: number): void {
  emit('update:monoPenSlot', index)
}

// ============================== ALGO + PARAMS ==============================
// Bridge between the AlgoParamsForm schema (algo-shape keys like
// ``angle_deg``) and the scattered BitmapDraft fields (e.g.
// ``crosshatch_angle_deg``). buildAlgorithmOptions in SourceSection
// uses the same mapping to pack /upload payloads, so writing back via
// onAlgoOption keeps the draft consistent end-to-end.
const FIELD_MAP: Record<string, Record<string, string>> = {
  halftone: { cell_size_px: 'cell_size_px' },
  stippling: { density: 'density', dot_radius_px: 'dot_radius_px', seed: 'seed' },
  crosshatch: {
    angle_deg: 'crosshatch_angle_deg',
    spacing_px: 'crosshatch_spacing_px',
    crossed: 'crosshatch_crossed',
  },
  contours: { spacing_px: 'contours_spacing_px', max_rings: 'contours_max_rings' },
  edges: { stroke_width: 'edges_stroke_width' },
  spiral: { spacing_px: 'spiral_spacing_px', samples_per_turn: 'spiral_samples_per_turn' },
  scanlines: {
    spacing_px: 'scanlines_spacing_px',
    wave_amp_px: 'scanlines_wave_amp_px',
    wave_period_px: 'scanlines_wave_period_px',
  },
  tsp: { density: 'density', seed: 'seed' },
}

const algoValues = computed<Record<string, unknown>>(() => {
  const map = FIELD_MAP[props.bitmap.algorithm] ?? {}
  const out: Record<string, unknown> = {}
  for (const [schemaKey, draftKey] of Object.entries(map)) {
    out[schemaKey] = props.bitmap[draftKey]
  }
  return out
})

function onPickStyle(style: PrintStyle): void {
  props.bitmap.algorithm = style.algorithm
  const map = FIELD_MAP[style.algorithm] ?? {}
  // Seed the scattered fields from the preset so the very first
  // /preview round-trip already exercises sensible knobs.
  for (const [schemaKey, draftKey] of Object.entries(map)) {
    if (schemaKey in style.algorithm_options) {
      props.bitmap[draftKey] = style.algorithm_options[schemaKey]
    }
  }
}

function onResetStyle(): void {
  // "Default" in mono context = crosshatch (best general-purpose shading
  // for a pen plotter). Direct doesn't suit mono because it produces
  // filled regions, not shaded lines.
  props.bitmap.algorithm = 'crosshatch'
}

function onAlgoOption(key: string, value: unknown): void {
  const draftKey = FIELD_MAP[props.bitmap.algorithm]?.[key]
  if (draftKey) props.bitmap[draftKey] = value
}

// ============================== DETAIL LEVEL ==============================
// max_dimension_px is the longest-edge resize cap applied before
// segmentation. Higher = more detail, slower preview. 4 named tiers
// instead of a raw number input so the operator can reach for
// "high detail" without thinking about pixels.
interface DetailLevel {
  id: 'fast' | 'standard' | 'high' | 'ultra'
  value: number
  labelKey: string
}
const detailLevels: DetailLevel[] = [
  { id: 'fast', value: 400, labelKey: 'mono.detailFast' },
  { id: 'standard', value: 800, labelKey: 'mono.detailStandard' },
  { id: 'high', value: 1200, labelKey: 'mono.detailHigh' },
  { id: 'ultra', value: 2000, labelKey: 'mono.detailUltra' },
]

// Snap a free-form max_dimension to the nearest preset for the highlight.
const currentDetail = computed<DetailLevel['id']>(() => {
  const target = props.bitmap.max_dimension_px
  let best = detailLevels[0]!
  let bestDelta = Math.abs(best.value - target)
  for (const level of detailLevels.slice(1)) {
    const delta = Math.abs(level.value - target)
    if (delta < bestDelta) {
      best = level
      bestDelta = delta
    }
  }
  return best.id
})

function setDetail(value: number): void {
  props.bitmap.max_dimension_px = value
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
    <!-- Pen slot -->
    <div class="space-y-1">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.pen') }}</p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="slot in penSlots"
          :key="slot.index"
          type="button"
          class="flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] transition"
          :class="monoPenSlot === slot.index
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
          :title="slot.installed ? slot.name : t('mono.penNotInstalled')"
          @click="setSlot(slot.index)"
        >
          <span
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: slot.color }"
          />
          <span class="font-mono text-[10px] text-slate-500">#{{ slot.index }}</span>
          <span class="truncate">{{ slot.name }}</span>
          <span v-if="!slot.installed" class="text-[9px] text-amber-400">·</span>
        </button>
      </div>
    </div>

    <!-- Number of shades -->
    <div class="space-y-1">
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

    <!-- Detail level -->
    <div class="space-y-1">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.detail') }}</p>
      <div class="grid grid-cols-4 gap-1">
        <button
          v-for="level in detailLevels"
          :key="level.id"
          type="button"
          class="rounded border px-1 py-1 text-[10px] transition"
          :class="currentDetail === level.id
            ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
            : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
          @click="setDetail(level.value)"
        >
          {{ t(level.labelKey) }}
          <span class="block font-mono text-[9px] text-slate-500">{{ level.value }}px</span>
        </button>
      </div>
      <p class="text-[10px] text-slate-500">{{ t('mono.detailHint') }}</p>
    </div>

    <!-- Render style + params -->
    <div class="space-y-1.5">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('mono.style') }}</p>
      <PrintStylePicker
        kind="image"
        :current-algorithm="bitmap.algorithm"
        @select="onPickStyle"
        @reset="onResetStyle"
      />
      <div
        v-if="bitmap.algorithm && bitmap.algorithm !== 'direct'"
        class="rounded border border-slate-700 bg-slate-900/50 p-2"
      >
        <AlgoParamsForm
          :algorithm="bitmap.algorithm"
          :values="algoValues"
          @update="onAlgoOption"
        />
      </div>
    </div>

    <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400">
      {{ t('mono.layersHint') }}
    </p>
  </div>
</template>
