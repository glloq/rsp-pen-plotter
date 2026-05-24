<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  resolveMasterStyle,
  type SegmentationMethod,
} from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

// Per-style knobs exposed by the active master style. Two paths:
//   - shaded styles (luminance_bands)   → bands slider (2..6) + the
//                                          monochrome ink colour picker
//                                          + style-specific range knobs
//                                          (spacing, angles, density)
//                                          + per-band override drawer.
//   - binary styles (thresholds)        → single threshold slider
//                                          (0.1..0.9) + ink colour
//                                          picker + optional stroke
//                                          width slider.
//
// Each "shaded" knob group writes into useBitmapDraft._mono.perStyle[id]
// via setMonoKnob; ``buildBandRecipes`` re-reads them on every /preview
// scheduling so live tweaks reflect immediately.

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
const usesBands = computed(
  () => style.value.segmentation?.method === 'luminance_bands',
)

const thresholdValue = computed({
  get: () => props.bitmap.thresholds[0] ?? 0.5,
  set: (v: number) => {
    props.bitmap.thresholds = [Math.max(0, Math.min(1, v))]
    draft.markSegmentationTouched('thresholds')
  },
})

function setNumBands(value: number): void {
  props.bitmap.num_bands = value
  draft.markSegmentationTouched('num_bands')
}

// ---- Mono ink colour ----
const inkColor = computed({
  get: () => draft.mono.value.ink_color,
  set: (v: string) => draft.setMonoInkColor(v),
})

// ---- Per-style knob accessors ----
// Reading via computed keeps the template terse and reactive. Setting
// goes through the composable's setter so future hooks (analytics,
// validation) have one place to land.
const knobs = computed(() => draft.getMonoStyleKnobs(props.styleId))

function setKnob<K extends string>(key: K, value: unknown): void {
  // The composable's setMonoKnob is generic over keyof MonoStyleKnobs;
  // we widen here for the template's sake since each call site already
  // knows the field name + type from the <input> binding.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(draft.setMonoKnob as any)(props.styleId, key, value)
}

// ---- Pencil angle chips ----
const PENCIL_ANGLE_OPTIONS = [0, 45, 90, 135] as const
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

// ---- Per-band override drawer ----
const bandIndices = computed(() => {
  if (!usesBands.value) return []
  return Array.from({ length: props.bitmap.num_bands }, (_, i) => i)
})

function bandPreview(i: number): Record<string, unknown> {
  // Show the literal pinned override if present, else the interpolated
  // value the operator would get without an override.
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

// ---- Per-band luminance swatch (visual cue: darkest → lightest) ----
function bandSwatchStyle(i: number): Record<string, string> {
  // Darker bands first (i=0 darkest), interpolate to near-white at the
  // brightest band. Pure visual reference — operators recognise which
  // card maps to which gray.
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

    <!-- Bands slider (shaded styles) -->
    <div v-if="usesBands" class="space-y-1">
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
        min="2"
        max="6"
        step="1"
        class="w-full accent-emerald-500"
        @input="(e) => setNumBands(Number((e.target as HTMLInputElement).value))"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.shadesHint') }}</p>
    </div>

    <!-- Threshold slider (binary styles) -->
    <div v-else class="space-y-1">
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
        min="0.1"
        max="0.9"
        step="0.05"
        class="w-full accent-emerald-500"
      />
      <p class="text-[10px] text-slate-500">{{ t('mono.thresholdHint') }}</p>
    </div>

    <!-- ===== Pencil: angle chips + spacing range + crossed toggle ===== -->
    <div v-if="styleId === 'pencil'" class="space-y-2 border-t border-slate-800 pt-3">
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
            :class="isAngleActive(a)
              ? 'border-emerald-500 bg-emerald-500/20 text-emerald-200'
              : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500'"
            @click="toggleAngle(a)"
          >{{ a }}°</button>
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.anglesHint') }}</p>
      </div>

      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spacingRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="1" max="10" step="0.5"
            :value="knobs.spacing_min ?? 2.5"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="1" max="10" step="0.5"
            :value="knobs.spacing_max ?? 6.5"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.spacingRangeHint') }}</p>
      </div>

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
    <div v-else-if="styleId === 'halftone-shade'" class="space-y-2 border-t border-slate-800 pt-3">
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.cellRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="2" max="14" step="1"
            :value="knobs.cell_min ?? 3"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('cell_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="2" max="14" step="1"
            :value="knobs.cell_max ?? 9"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('cell_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.cellRangeHint') }}</p>
      </div>
    </div>

    <!-- ===== Stippling shade: density range + dot radius ===== -->
    <div v-else-if="styleId === 'stippling-shade'" class="space-y-2 border-t border-slate-800 pt-3">
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.densityRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="0.005" max="0.1" step="0.001"
            :value="knobs.density_min ?? 0.012"
            class="w-20 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('density_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="0.005" max="0.1" step="0.001"
            :value="knobs.density_max ?? 0.06"
            class="w-20 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('density_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.densityRangeHint') }}</p>
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.dotRadius') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{ (knobs.dot_radius ?? 0.5).toFixed(2) }}</span>
        </p>
        <input
          type="range" min="0.3" max="1.5" step="0.05"
          :value="knobs.dot_radius ?? 0.5"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('dot_radius', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Engraving: spacing range + wave amp range ===== -->
    <div v-else-if="styleId === 'engraving'" class="space-y-2 border-t border-slate-800 pt-3">
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spacingRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="1" max="8" step="0.5"
            :value="knobs.spacing_min ?? 1.8"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="1" max="8" step="0.5"
            :value="knobs.spacing_max ?? 5"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.waveRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="0" max="3" step="0.1"
            :value="knobs.wave_min ?? 0.6"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('wave_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="0" max="3" step="0.1"
            :value="knobs.wave_max ?? 1.6"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('wave_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </div>

    <!-- ===== Contours-topo: spacing range + rings range ===== -->
    <div v-else-if="styleId === 'contours-topo'" class="space-y-2 border-t border-slate-800 pt-3">
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.spacingRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="1" max="8" step="0.5"
            :value="knobs.spacing_min ?? 2.5"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="1" max="8" step="0.5"
            :value="knobs.spacing_max ?? 6"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('spacing_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.ringsRange') }}
        </p>
        <div class="flex items-center gap-2">
          <span class="text-[10px] text-slate-500">{{ t('mono.minLabel') }}</span>
          <input
            type="number" min="5" max="40" step="1"
            :value="knobs.rings_min ?? 10"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('rings_min', Number((e.target as HTMLInputElement).value))"
          />
          <span class="text-[10px] text-slate-500">{{ t('mono.maxLabel') }}</span>
          <input
            type="number" min="5" max="40" step="1"
            :value="knobs.rings_max ?? 30"
            class="w-16 rounded border border-slate-700 bg-slate-900 px-1 py-0.5 text-[11px] font-mono text-slate-200"
            @input="(e) => setKnob('rings_max', Number((e.target as HTMLInputElement).value))"
          />
        </div>
        <p class="text-[10px] text-slate-500">{{ t('mono.ringsRangeHint') }}</p>
      </div>
    </div>

    <!-- ===== Binary styles (outline / centerline / spiral / tsp): stroke width ===== -->
    <div
      v-else-if="!usesBands && (styleId === 'outline' || styleId === 'centerline-trace')"
      class="space-y-1 border-t border-slate-800 pt-3"
    >
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('mono.strokeWidth') }}
        <span class="ml-1 font-mono text-[11px] text-slate-300">{{ (knobs.stroke_width ?? 0.8).toFixed(2) }}</span>
      </p>
      <input
        type="range" min="0.4" max="2.0" step="0.1"
        :value="knobs.stroke_width ?? 0.8"
        class="w-full accent-emerald-500"
        @input="(e) => setKnob('stroke_width', Number((e.target as HTMLInputElement).value))"
      />
    </div>

    <!-- ===== Per-band override drawer (shaded styles only) ===== -->
    <details v-if="usesBands" class="border-t border-slate-800 pt-3">
      <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-slate-400 hover:text-slate-200">
        {{ t('mono.perBandOverrides') }}
      </summary>
      <p class="mt-1 text-[10px] text-slate-500">{{ t('mono.perBandHint') }}</p>
      <div class="mt-2 space-y-2">
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
              >pinned</span>
            </div>
            <button
              v-if="isBandPinned(i)"
              type="button"
              :title="t('mono.resetBand')"
              class="rounded border border-slate-700 px-2 text-[11px] text-slate-300 hover:border-emerald-500 hover:text-emerald-300"
              @click="resetBand(i)"
            >↺</button>
          </div>
          <!-- Render the same numeric fields as the relevant interpolated
               option keys, so the operator pins whichever knob they care
               about for this specific band. Generic key-value editor
               keeps the drawer style-agnostic. -->
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
                @input="(e) => pinBand(i, String(key), Number((e.target as HTMLInputElement).value))"
              />
              <span
                v-else-if="Array.isArray(value)"
                class="font-mono text-[10px] text-slate-400"
                :title="String(value)"
              >[{{ (value as unknown[]).join(',') }}]</span>
              <span v-else class="font-mono text-[10px] text-slate-400">{{ String(value) }}</span>
            </label>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>
