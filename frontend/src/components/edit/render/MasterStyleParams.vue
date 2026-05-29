<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMasterStyle, type SegmentationMethod } from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import DualRangeSlider from './DualRangeSlider.vue'

// Per-style knobs exposed by the active master style. Two paths:
//   - shaded styles (luminance_bands)   → bands slider (1..20) + ink
//                                          colour + ONE compact range
//                                          slider per dimension
//                                          (spacing, density, cell,
//                                          rings, wave amplitude).
//   - binary styles (thresholds)        → single threshold slider +
//                                          ink colour + ONE single
//                                          slider for the only knob
//                                          that drives darkness on
//                                          that style (stroke width,
//                                          dot density, spiral spacing).
//
// Per-band override drawer is only shown when ``mono.advanced_mode``
// is on — the default UI stays focused on the global sliders.

interface BitmapLike {
  num_bands: number
  thresholds: number[]
  segmentation_method: SegmentationMethod
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
  styleId: string
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

const style = computed(() => resolveMasterStyle(props.styleId))
const usesBands = computed(() => style.value.segmentation?.method === 'luminance_bands')
// Some luminance_bands styles don't expose a band-count knob (the tonal
// spiral is a single continuous stroke shaded from the pixel tone map, so
// its band count is fixed at 1). Hide the bands slider + per-band drawer
// for those.
const knobBands = computed(() => style.value.segmentation?.knob_bands !== false)

const thresholdValue = computed({
  get: () => props.bitmap.thresholds[0] ?? 0.5,
  set: (v: number) => {
    props.bitmap.thresholds = [Math.max(0, Math.min(1, v))]
    draft.markSegmentationTouched('thresholds')
  },
})

function setNumBands(value: number): void {
  // Delegate to the draft so the background-drop threshold is auto-tuned
  // to the new band count (keeps the near-white paper band dropped at any
  // N instead of hatching the background at low counts).
  draft.setNumBands(value)
}

// ---- Mono ink colour ----
const inkColor = computed({
  get: () => draft.mono.value.ink_color,
  set: (v: string) => draft.setMonoInkColor(v),
})

const advancedMode = computed({
  get: () => draft.mono.value.advanced_mode,
  set: (v: boolean) => draft.setMonoAdvancedMode(v),
})

// ---- Per-style knob accessors ----
const knobs = computed(() => draft.getMonoStyleKnobs(props.styleId))

function setKnob<K extends string>(key: K, value: unknown): void {
  // The composable's setMonoKnob is generic over keyof MonoStyleKnobs;
  // widening here keeps the template terse while every call site
  // already knows the field name + type from its <input> binding.

  ;(draft.setMonoKnob as any)(props.styleId, key, value)
}

// ---- Pencil angle chips ----
const PENCIL_ANGLE_OPTIONS = [0, 30, 45, 90, 135, 150] as const
function toggleAngle(angle: number): void {
  const current = [...(knobs.value.angles ?? [])]
  const idx = current.indexOf(angle)
  if (idx >= 0) {
    // Keep at least one angle so the band recipe always has something to draw.
    if (current.length <= 1) return
    current.splice(idx, 1)
  } else {
    if (current.length >= 4) return
    current.push(angle)
  }
  setKnob('angles', current)
}
function isAngleActive(angle: number): boolean {
  return (knobs.value.angles ?? []).includes(angle)
}

// ---- Per-band override drawer (advanced only) ----
const bandIndices = computed(() => {
  if (!usesBands.value) return []
  return Array.from({ length: props.bitmap.num_bands }, (_, i) => i)
})

function bandPreview(i: number): Record<string, unknown> {
  const pinned = knobs.value.perBand?.[i]
  if (pinned) return pinned
  return draft.interpolatedBandOptions(i, props.bitmap.num_bands)
}

function isBandPinned(i: number): boolean {
  return !!knobs.value.perBand?.[i]
}

function pinBand(i: number, key: string, value: unknown): void {
  const base = { ...bandPreview(i) }
  base[key] = value
  draft.setMonoBandOverride(props.styleId, i, base)
}

function resetBand(i: number): void {
  draft.setMonoBandOverride(props.styleId, i, null)
}

function bandSwatchStyle(i: number): Record<string, string> {
  // Darker bands first (i=0 darkest), interpolating toward near-white
  // at the brightest. Pure visual reference — lets the operator map
  // each card to its target gray level at a glance.
  const total = Math.max(1, props.bitmap.num_bands - 1)
  const t = total === 0 ? 0 : i / total
  const v = Math.round(60 + t * 180)
  return { backgroundColor: `rgb(${v},${v},${v})` }
}
</script>

<template>
  <div class="space-y-3">
    <!-- Mono ink colour (always shown for mono master styles) -->
    <div class="flex items-center justify-between gap-2">
      <div class="flex-1">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.inkColor') }}
        </p>
        <p class="text-[10px] text-slate-500">{{ t('mono.inkColorHint') }}</p>
      </div>
      <input
        v-model="inkColor"
        type="color"
        class="h-8 w-12 cursor-pointer rounded border border-slate-700 bg-slate-900"
      />
    </div>

    <!-- Bands slider (shaded styles with a band-count knob) -->
    <div v-if="usesBands && knobBands" class="space-y-1">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.shades') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </p>
        <span class="font-mono text-[11px] text-slate-300">{{ bitmap.num_bands }}</span>
      </div>
      <input
        :value="bitmap.num_bands"
        type="range"
        min="1"
        max="20"
        step="1"
        class="w-full accent-emerald-500"
        @input="(e) => setNumBands(Number((e.target as HTMLInputElement).value))"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.shadesHint') }}</p>
    </div>

    <!-- Threshold slider (binary styles) -->
    <div v-else-if="!usesBands" class="space-y-1">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.threshold') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </p>
        <span class="font-mono text-[11px] text-slate-300">{{ thresholdValue.toFixed(2) }}</span>
      </div>
      <input
        v-model.number="thresholdValue"
        type="range"
        min="0.05"
        max="0.95"
        step="0.05"
        class="w-full accent-emerald-500"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.thresholdHint') }}</p>
    </div>

    <!-- ===== Pencil / Hatch-fill / Scribble: angle chips + spacing + crossed ===== -->
    <div
      v-if="styleId === 'pencil' || styleId === 'hatch-fill' || styleId === 'scribble'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.angles') }}
        </p>
        <div class="mt-1 flex gap-1">
          <button
            v-for="a in PENCIL_ANGLE_OPTIONS"
            :key="a"
            type="button"
            class="rounded border px-2 py-1 text-[11px] font-mono"
            :class="
              isAngleActive(a)
                ? 'border-emerald-500 bg-emerald-500/20 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500'
            "
            @click="toggleAngle(a)"
          >
            {{ a }}°
          </button>
        </div>
        <p class="mt-1 text-[10px] text-slate-500">{{ t('mono.anglesHint') }}</p>
      </div>

      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6.5"
        :min="1"
        :max="10"
        :step="0.5"
        unit="px"
        @update:model-value-min="(v) => setKnob('spacing_min', v)"
        @update:model-value-max="(v) => setKnob('spacing_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.spacingRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('mono.spacingRangeHint') }}</p>
        </template>
      </DualRangeSlider>

      <label class="flex items-center gap-2 text-[11px] text-slate-300">
        <input
          type="checkbox"
          class="accent-emerald-500"
          :checked="knobs.crossed_on_darkest ?? true"
          @change="(e) => setKnob('crossed_on_darkest', (e.target as HTMLInputElement).checked)"
        />
        {{ t('mono.crossedOnDarkest') }}
      </label>
    </div>

    <!-- ===== Halftone shade: cell size range ===== -->
    <DualRangeSlider
      v-else-if="styleId === 'halftone-shade'"
      class="border-t border-slate-800 pt-3"
      :model-value-min="knobs.cell_min ?? 3"
      :model-value-max="knobs.cell_max ?? 9"
      :min="2"
      :max="14"
      :step="1"
      unit="px"
      @update:model-value-min="(v) => setKnob('cell_min', v)"
      @update:model-value-max="(v) => setKnob('cell_max', v)"
    >
      <template #label>
        <span class="uppercase tracking-wider">{{ t('mono.cellRange') }}</span>
      </template>
      <template #hint>
        <p class="text-[10px] text-slate-500">{{ t('mono.cellRangeHint') }}</p>
      </template>
    </DualRangeSlider>

    <!-- ===== Stippling / Voronoi shade: density range + dot radius ===== -->
    <div
      v-else-if="styleId === 'stippling-shade' || styleId === 'voronoi-shade'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.density_min ?? 0.012"
        :model-value-max="knobs.density_max ?? 0.15"
        :min="0.005"
        :max="0.5"
        :step="0.002"
        @update:model-value-min="(v) => setKnob('density_min', v)"
        @update:model-value-max="(v) => setKnob('density_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('mono.densityRangeHint') }}</p>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.dotRadius') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            (knobs.dot_radius ?? 0.5).toFixed(2)
          }}</span>
        </p>
        <input
          type="range"
          min="0.3"
          max="1.5"
          step="0.05"
          :value="knobs.dot_radius ?? 0.5"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('dot_radius', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Engraving / Squiggle: spacing range + wave amp range + period ===== -->
    <div
      v-else-if="styleId === 'engraving' || styleId === 'squiggle-shade'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 1.8"
        :model-value-max="knobs.spacing_max ?? 5"
        :min="1"
        :max="8"
        :step="0.5"
        unit="px"
        @update:model-value-min="(v) => setKnob('spacing_min', v)"
        @update:model-value-max="(v) => setKnob('spacing_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.spacingRange') }}</span>
        </template>
      </DualRangeSlider>
      <DualRangeSlider
        :model-value-min="knobs.wave_min ?? 0.6"
        :model-value-max="knobs.wave_max ?? 1.6"
        :min="0"
        :max="3"
        :step="0.1"
        unit="px"
        @update:model-value-min="(v) => setKnob('wave_min', v)"
        @update:model-value-max="(v) => setKnob('wave_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.waveRange') }}</span>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.wavePeriod') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.wave_period ?? 14) }} px</span
          >
        </p>
        <input
          type="range"
          min="8"
          max="20"
          step="1"
          :value="knobs.wave_period ?? 14"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('wave_period', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Contours-topo: spacing range + rings range ===== -->
    <div v-else-if="styleId === 'contours-topo'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6"
        :min="1"
        :max="8"
        :step="0.5"
        unit="px"
        @update:model-value-min="(v) => setKnob('spacing_min', v)"
        @update:model-value-max="(v) => setKnob('spacing_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.spacingRange') }}</span>
        </template>
      </DualRangeSlider>
      <DualRangeSlider
        :model-value-min="knobs.rings_min ?? 10"
        :model-value-max="knobs.rings_max ?? 30"
        :min="5"
        :max="40"
        :step="1"
        @update:model-value-min="(v) => setKnob('rings_min', v)"
        @update:model-value-max="(v) => setKnob('rings_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.ringsRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('mono.ringsRangeHint') }}</p>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Concentric rings: spacing range + rings range ===== -->
    <div
      v-else-if="styleId === 'concentric-rings'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 3"
        :model-value-max="knobs.spacing_max ?? 6"
        :min="1"
        :max="10"
        :step="1"
        unit="px"
        @update:model-value-min="(v) => setKnob('spacing_min', v)"
        @update:model-value-max="(v) => setKnob('spacing_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.spacingRange') }}</span>
        </template>
      </DualRangeSlider>
      <DualRangeSlider
        :model-value-min="knobs.rings_min ?? 12"
        :model-value-max="knobs.rings_max ?? 50"
        :min="2"
        :max="80"
        :step="1"
        @update:model-value-min="(v) => setKnob('rings_min', v)"
        @update:model-value-max="(v) => setKnob('rings_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.ringsRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('mono.ringsRangeHint') }}</p>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Low-poly: point density range ===== -->
    <DualRangeSlider
      v-else-if="styleId === 'lowpoly'"
      class="border-t border-slate-800 pt-3"
      :model-value-min="knobs.density_min ?? 0.006"
      :model-value-max="knobs.density_max ?? 0.04"
      :min="0.002"
      :max="0.1"
      :step="0.002"
      @update:model-value-min="(v) => setKnob('density_min', v)"
      @update:model-value-max="(v) => setKnob('density_max', v)"
    >
      <template #label>
        <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
      </template>
      <template #hint>
        <p class="text-[10px] text-slate-500">{{ t('mono.densityRangeHint') }}</p>
      </template>
    </DualRangeSlider>

    <!-- ===== Flow-field / Hilbert: spacing range only ===== -->
    <!-- (gosper-fill has no spacing knob — its tone is the L-system order,
         lerped by the registry bandRecipe; a spacing slider would be a no-op) -->
    <DualRangeSlider
      v-else-if="styleId === 'flowfield-master' || styleId === 'hilbert-fill'"
      class="border-t border-slate-800 pt-3"
      :model-value-min="knobs.spacing_min ?? 4"
      :model-value-max="knobs.spacing_max ?? 12"
      :min="1"
      :max="20"
      :step="0.5"
      unit="px"
      @update:model-value-min="(v) => setKnob('spacing_min', v)"
      @update:model-value-max="(v) => setKnob('spacing_max', v)"
    >
      <template #label>
        <span class="uppercase tracking-wider">{{ t('mono.spacingRange') }}</span>
      </template>
      <template #hint>
        <p class="text-[10px] text-slate-500">{{ t('mono.spacingRangeHint') }}</p>
      </template>
    </DualRangeSlider>

    <!-- ===== TSP / TSP-optimised: dot density (single knob — binary mono) ===== -->
    <div
      v-else-if="styleId === 'tsp' || styleId === 'tsp-optimized'"
      class="space-y-1 border-t border-slate-800 pt-3"
    >
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('mono.dotDensity') }}
        <span class="ml-1 font-mono text-[11px] text-slate-300">{{
          (knobs.density ?? 0.04).toFixed(3)
        }}</span>
      </p>
      <input
        type="range"
        min="0.01"
        max="0.1"
        step="0.005"
        :value="knobs.density ?? 0.04"
        class="w-full accent-emerald-500"
        @input="(e) => setKnob('density', Number((e.target as HTMLInputElement).value))"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.dotDensityHint') }}</p>
    </div>

    <!-- ===== Spiral (tonal): spacing + wobble wavelength + strength ===== -->
    <div v-else-if="styleId === 'spiral-master'" class="space-y-3 border-t border-slate-800 pt-3">
      <p class="text-[10px] leading-snug text-slate-500">{{ t('mono.spiralTonalHint') }}</p>
      <div class="space-y-1">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spiralSpacing') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.spacing_px ?? 14).toFixed(0) }} px</span
          >
        </p>
        <input
          type="range"
          min="3"
          max="30"
          step="1"
          :value="knobs.spacing_px ?? 14"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('spacing_px', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('mono.spiralSpacingHint') }}</p>
      </div>

      <div class="space-y-1">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spiralWavelength') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.wavelength_px ?? 10).toFixed(0) }} px</span
          >
        </p>
        <input
          type="range"
          min="2"
          max="24"
          step="1"
          :value="knobs.wavelength_px ?? 10"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('wavelength_px', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('mono.spiralWavelengthHint') }}</p>
      </div>

      <div class="space-y-1">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spiralStrength') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round((knobs.tone_strength ?? 1) * 100)
          }}%</span>
        </p>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="knobs.tone_strength ?? 1"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('tone_strength', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('mono.spiralStrengthHint') }}</p>
      </div>
    </div>

    <!-- ===== Outline / Centerline: stroke width (binary mono) ===== -->
    <div
      v-else-if="styleId === 'outline' || styleId === 'centerline-trace'"
      class="space-y-1 border-t border-slate-800 pt-3"
    >
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('mono.strokeWidth') }}
        <span class="ml-1 font-mono text-[11px] text-slate-300">{{
          (knobs.stroke_width ?? 0.8).toFixed(2)
        }}</span>
      </p>
      <input
        type="range"
        min="0.4"
        max="2.0"
        step="0.1"
        :value="knobs.stroke_width ?? 0.8"
        class="w-full accent-emerald-500"
        @input="(e) => setKnob('stroke_width', Number((e.target as HTMLInputElement).value))"
      />
    </div>

    <!-- ===== Advanced mode toggle + per-band drawer ===== -->
    <div v-if="usesBands && knobBands" class="border-t border-slate-800 pt-3">
      <label class="flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
        <input v-model="advancedMode" type="checkbox" class="accent-emerald-500" />
        <span class="uppercase tracking-wider text-slate-400">{{ t('mono.advancedMode') }}</span>
      </label>
      <p class="mt-1 text-[10px] text-slate-500">{{ t('mono.advancedModeHint') }}</p>

      <div v-if="advancedMode" class="mt-3 space-y-2">
        <p class="text-[10px] text-slate-500">{{ t('mono.perBandHint') }}</p>
        <div
          v-for="i in bandIndices"
          :key="i"
          class="rounded border border-slate-800 bg-slate-900/50 p-2"
        >
          <div class="mb-1 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="h-3 w-3 rounded" :style="bandSwatchStyle(i)" />
              <span class="text-[11px] text-slate-300">
                {{ t('mono.bandLabel', { n: i + 1 }) }}
              </span>
              <span
                v-if="isBandPinned(i)"
                class="rounded bg-amber-500/20 px-1 text-[9px] uppercase text-amber-300"
                >pinned</span
              >
            </div>
            <button
              v-if="isBandPinned(i)"
              type="button"
              :title="t('mono.resetBand')"
              class="rounded border border-slate-700 px-2 text-[11px] text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
              @click="resetBand(i)"
            >
              ↺
            </button>
          </div>
          <div class="grid grid-cols-2 gap-1">
            <label
              v-for="(value, key) in bandPreview(i)"
              :key="key"
              class="flex items-center gap-1"
            >
              <span class="text-[10px] text-slate-500">{{ key }}</span>
              <input
                v-if="typeof value === 'number'"
                type="number"
                :value="value"
                step="any"
                class="w-full rounded border border-slate-700 bg-slate-950 px-1 py-0.5 text-[11px] font-mono text-slate-200"
                @input="
                  (e) => pinBand(i, String(key), Number((e.target as HTMLInputElement).value))
                "
              />
              <span
                v-else-if="Array.isArray(value)"
                class="font-mono text-[10px] text-slate-400"
                :title="String(value)"
                >[{{ (value as unknown[]).join(',') }}]</span
              >
              <span v-else class="font-mono text-[10px] text-slate-400">{{ String(value) }}</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
