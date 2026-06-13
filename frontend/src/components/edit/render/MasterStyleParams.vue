<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMasterStyle, type SegmentationMethod } from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { useJobStore } from '../../../stores/job'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import MasterStyleKnobs from './MasterStyleKnobs.vue'

// Per-style knobs exposed by the active master style. Two paths:
//   - shaded styles (luminance_bands)   → bands slider (1..20) + ink
//                                          colour + the per-style knob
//                                          block.
//   - binary styles (thresholds)        → single threshold slider +
//                                          ink colour + the per-style
//                                          knob block.
//
// The per-style knob UI itself (which sliders, bounds, labels) is
// declarative — ``data/styleKnobs.ts`` descriptors rendered by the
// shared ``MasterStyleKnobs`` component — so a new master style needs
// zero edits here. This card keeps only the mono-specific chrome: ink
// colour, bands/threshold, and the advanced per-band override drawer
// (only shown when ``mono.advanced_mode`` is on).

interface BitmapLike {
  num_bands: number
  thresholds: number[]
  segmentation_method: SegmentationMethod
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
  styleId: string
  /** Pen tip diameter (mm) of the mono ink, floors physical mark knobs. */
  minPenWidthMm?: number | null
}>()

const { t } = useI18n()
const draft = useBitmapDraft()
const store = useJobStore()

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

// Trailing-edge throttle for the layer propagation below. A slider
// drag emits one @input per pixel; patching every layer's
// ``layer_algorithms`` on each of those floods the store with writes
// while the knob itself (``draft.setMonoKnob``) already gives the
// operator immediate visual feedback. One propagation ~120ms after
// the last input event is enough for /rerender consistency.
const KNOB_PROPAGATION_DELAY_MS = 120
let knobPropagationTimer: ReturnType<typeof setTimeout> | null = null

function setKnob<K extends string>(key: K, value: unknown): void {
  // The composable's setMonoKnob is generic over keyof MonoStyleKnobs;
  // widening here keeps the template terse while every call site
  // already knows the field name + type from its <input> binding.

  ;(draft.setMonoKnob as any)(props.styleId, key, value)
  // Re-propagate the updated knobs onto existing layers so /rerender
  // (gcode generation) matches the live /preview. /preview rebuilds
  // ``band_recipes`` from current knobs on every call; ``layer_algorithms``
  // would otherwise stay frozen on the values captured at upload time.
  if (store.layers.length > 0) {
    if (knobPropagationTimer !== null) clearTimeout(knobPropagationTimer)
    knobPropagationTimer = setTimeout(() => {
      knobPropagationTimer = null
      void applyMasterStyleToLayers(store, {
        styleId: props.styleId,
        penSlot: draft.monoPenSlot.value,
        recipeResolver: (index, total) => draft.monoRecipeForBand(index, total),
      })
    }, KNOB_PROPAGATION_DELAY_MS)
  }
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

    <!-- ===== Per-style knob block — declarative (data/styleKnobs.ts) ===== -->
    <MasterStyleKnobs
      family="mono"
      :style-id="styleId"
      :knobs="knobs"
      :min-pen-width-mm="minPenWidthMm"
      @set="setKnob"
    />

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
