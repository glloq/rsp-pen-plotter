<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMulticolorStyle } from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import DualRangeSlider from './DualRangeSlider.vue'

// Per-style operator knobs for the multicolour master family — twin of
// ``MasterStyleParams.vue`` but for the colour-recipe pipeline. Each
// style exposes the same shape of compact range slider / single slider
// the mono variant uses so the two sides of the StyleTab feel
// symmetric. ``num_colors`` lives on the PaletteCard (it gates the
// palette editor too) so this card focuses purely on per-style knobs.

interface BitmapLike {
  num_colors: number
  palette: string[]
  segmentation_method: string
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
  styleId: string
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

const style = computed(() => resolveMulticolorStyle(props.styleId))

const knobs = computed(() => draft.getMulticolorStyleKnobs(props.styleId))

function setKnob<K extends string>(key: K, value: unknown): void {
  ;(draft.setMulticolorKnob as any)(props.styleId, key, value)
}

// Cluster count surfaced at the top so the operator gets the same
// orientation cue as the mono card's "bands" slider. Writes go through
// the bitmap draft directly — same path the PaletteCard uses.
const numColors = computed({
  get: () => props.bitmap.num_colors,
  set: (v: number) => {
    props.bitmap.num_colors = Math.max(1, Math.min(16, Math.round(v)))
    draft.markSegmentationTouched('num_bands') // close enough family
  },
})

// fixed_palette locks num_colors to the manual palette length — show
// the count but disable the slider so the operator isn't surprised
// when dragging it does nothing.
const numColorsLocked = computed(
  () => props.bitmap.segmentation_method === 'fixed_palette' && props.bitmap.palette.length > 0,
)

const effectiveColorCount = computed(() =>
  numColorsLocked.value ? props.bitmap.palette.length : props.bitmap.num_colors,
)
</script>

<template>
  <div class="space-y-3">
    <!-- Cluster count slider (twin of mono's "Shades") -->
    <div class="space-y-1">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('colorStyles.numColors') }}
          <LayerCountBadge :count="draft.expectedLayerCount.value" />
        </p>
        <span class="font-mono text-[11px] text-slate-300">{{ effectiveColorCount }}</span>
      </div>
      <input
        :value="numColors"
        type="range"
        :min="2"
        :max="16"
        step="1"
        :disabled="numColorsLocked"
        class="w-full accent-emerald-500 disabled:opacity-50"
        @input="(e) => (numColors = Number((e.target as HTMLInputElement).value))"
      />
      <p class="text-[10px] text-slate-500">
        {{ numColorsLocked ? t('colorStyles.numColorsLocked') : t('colorStyles.numColorsHint') }}
      </p>
    </div>

    <!-- ===== Flat: no tunable knobs, just a placeholder line ===== -->
    <p
      v-if="styleId === 'color-flat' || styleId === 'color-flat-lab'"
      class="rounded border border-slate-800 bg-slate-900/40 px-2 py-1.5 text-[10px] text-slate-500"
    >
      {{ t('colorStyles.flatNoKnobs') }}
    </p>

    <!-- ===== Colour crosshatch: spacing range + angle step + crossed ===== -->
    <div
      v-else-if="styleId === 'color-crosshatch'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6"
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
          <p class="text-[10px] text-slate-500">{{ t('colorStyles.crosshatchSpacingHint') }}</p>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('colorStyles.angleStep') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.angle_step ?? 45) }}°</span
          >
        </p>
        <input
          type="range"
          min="0"
          max="90"
          step="5"
          :value="knobs.angle_step ?? 45"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('angle_step', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('colorStyles.angleStepHint') }}</p>
      </div>
      <label class="flex items-center gap-2 text-[11px] text-slate-300">
        <input
          type="checkbox"
          class="accent-emerald-500"
          :checked="knobs.crossed ?? false"
          @change="(e) => setKnob('crossed', (e.target as HTMLInputElement).checked)"
        />
        {{ t('convert.crossed') }}
      </label>
    </div>

    <!-- ===== Colour stipple (Voronoi): density range + dot + iterations ===== -->
    <div v-else-if="styleId === 'color-stipple'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.density_min ?? 0.012"
        :model-value-max="knobs.density_max ?? 0.05"
        :min="0.005"
        :max="0.3"
        :step="0.001"
        @update:model-value-min="(v) => setKnob('density_min', v)"
        @update:model-value-max="(v) => setKnob('density_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
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
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.iterations') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.iterations ?? 4)
          }}</span>
        </p>
        <input
          type="range"
          min="0"
          max="20"
          step="1"
          :value="knobs.iterations ?? 4"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('iterations', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('colorStyles.iterationsHint') }}</p>
      </div>
    </div>

    <!-- ===== Halftone CMYK: single cell size — angles are derived from hue ===== -->
    <div
      v-else-if="styleId === 'color-halftone-cmyk'"
      class="space-y-1 border-t border-slate-800 pt-3"
    >
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('convert.cellSize') }}
        <span class="ml-1 font-mono text-[11px] text-slate-300"
          >{{ Math.round(knobs.cell_size ?? 5) }} px</span
        >
      </p>
      <input
        type="range"
        min="2"
        max="14"
        step="1"
        :value="knobs.cell_size ?? 5"
        class="w-full accent-emerald-500"
        @input="(e) => setKnob('cell_size', Number((e.target as HTMLInputElement).value))"
      />
      <p class="text-[10px] text-slate-500">{{ t('colorStyles.cmykHint') }}</p>
    </div>

    <!-- ===== Topo couleur: spacing + rings range ===== -->
    <div
      v-else-if="styleId === 'color-contours-topo'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
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
      </DualRangeSlider>
    </div>

    <!-- ===== Flowfield: seed spacing range + step + max_steps + noise + bidir ===== -->
    <div v-else-if="styleId === 'color-flowfield'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.seed_spacing_min ?? 6"
        :model-value-max="knobs.seed_spacing_max ?? 12"
        :min="2"
        :max="30"
        :step="0.5"
        unit="px"
        @update:model-value-min="(v) => setKnob('seed_spacing_min', v)"
        @update:model-value-max="(v) => setKnob('seed_spacing_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('colorStyles.seedSpacingRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('colorStyles.seedSpacingHint') }}</p>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.stepPx') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.step_px ?? 0.8).toFixed(1) }} px</span
          >
        </p>
        <input
          type="range"
          min="0.2"
          max="3"
          step="0.1"
          :value="knobs.step_px ?? 0.8"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('step_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.maxSteps') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.max_steps ?? 600)
          }}</span>
        </p>
        <input
          type="range"
          min="100"
          max="2000"
          step="50"
          :value="knobs.max_steps ?? 600"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('max_steps', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.noiseScale') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.noise_scale ?? 48)
          }}</span>
        </p>
        <input
          type="range"
          min="4"
          max="128"
          step="2"
          :value="knobs.noise_scale ?? 48"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('noise_scale', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <label class="flex items-center gap-2 text-[11px] text-slate-300">
        <input
          type="checkbox"
          class="accent-emerald-500"
          :checked="knobs.bidirectional ?? true"
          @change="(e) => setKnob('bidirectional', (e.target as HTMLInputElement).checked)"
        />
        {{ t('convert.bidirectional') }}
      </label>
    </div>

    <!-- ===== Croquis: spacing range + amplitude range + period + jitter ===== -->
    <div v-else-if="styleId === 'color-sketch'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 3"
        :model-value-max="knobs.spacing_max ?? 6"
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
      </DualRangeSlider>
      <DualRangeSlider
        :model-value-min="knobs.amp_min ?? 0.6"
        :model-value-max="knobs.amp_max ?? 1.8"
        :min="0.2"
        :max="4"
        :step="0.1"
        unit="px"
        @update:model-value-min="(v) => setKnob('amp_min', v)"
        @update:model-value-max="(v) => setKnob('amp_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('colorStyles.ampRange') }}</span>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('mono.wavePeriod') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.period_px ?? 8) }} px</span
          >
        </p>
        <input
          type="range"
          min="2"
          max="20"
          step="0.5"
          :value="knobs.period_px ?? 8"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('period_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.jitter') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            (knobs.jitter ?? 0.45).toFixed(2)
          }}</span>
        </p>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="knobs.jitter ?? 0.45"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('jitter', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Spirales offset: spacing range + max rings ===== -->
    <div v-else-if="styleId === 'color-spiral'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2"
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
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.maxRings') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.max_rings ?? 40)
          }}</span>
        </p>
        <input
          type="range"
          min="5"
          max="120"
          step="1"
          :value="knobs.max_rings ?? 40"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('max_rings', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Stippling classique couleur: density range + dot radius ===== -->
    <div
      v-else-if="styleId === 'color-stippling-classic'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.density_min ?? 0.012"
        :model-value-max="knobs.density_max ?? 0.05"
        :min="0.005"
        :max="0.3"
        :step="0.001"
        @update:model-value-min="(v) => setKnob('density_min', v)"
        @update:model-value-max="(v) => setKnob('density_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
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

    <!-- ===== Edges couleur: épaisseur de trait ===== -->
    <div v-else-if="styleId === 'color-edges'" class="space-y-1 border-t border-slate-800 pt-3">
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

    <!-- ===== Centerline couleur: stroke width + min branch ===== -->
    <div
      v-else-if="styleId === 'color-centerline'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <div>
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
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.minBranch') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.min_branch_px ?? 3) }} px</span
          >
        </p>
        <input
          type="range"
          min="1"
          max="20"
          step="1"
          :value="knobs.min_branch_px ?? 3"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('min_branch_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Spirale classique couleur: spacing range + samples/tour ===== -->
    <div
      v-else-if="styleId === 'color-spiral-classic'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2"
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
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.samplesPerTurn') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.samples_per_turn ?? 64)
          }}</span>
        </p>
        <input
          type="range"
          min="16"
          max="256"
          step="4"
          :value="knobs.samples_per_turn ?? 64"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('samples_per_turn', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Scanlines couleur: spacing range + wave amp + wave period ===== -->
    <div v-else-if="styleId === 'color-scanlines'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6"
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
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.waveAmp') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.wave_amp_px ?? 0).toFixed(1) }} px</span
          >
        </p>
        <input
          type="range"
          min="0"
          max="6"
          step="0.2"
          :value="knobs.wave_amp_px ?? 0"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('wave_amp_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.wavePeriod') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.wave_period_px ?? 12) }} px</span
          >
        </p>
        <input
          type="range"
          min="2"
          max="40"
          step="1"
          :value="knobs.wave_period_px ?? 12"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('wave_period_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== TSP couleur: density range ===== -->
    <div v-else-if="styleId === 'color-tsp'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.density_min ?? 0.012"
        :model-value-max="knobs.density_max ?? 0.05"
        :min="0.005"
        :max="0.3"
        :step="0.001"
        @update:model-value-min="(v) => setKnob('density_min', v)"
        @update:model-value-max="(v) => setKnob('density_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('colorStyles.tspHint') }}</p>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Hilbert couleur: spacing range + min run ===== -->
    <div v-else-if="styleId === 'color-hilbert'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6"
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
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.minRunPx') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.min_run_px ?? 3) }} px</span
          >
        </p>
        <input
          type="range"
          min="1"
          max="20"
          step="1"
          :value="knobs.min_run_px ?? 3"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('min_run_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Gosper couleur: ordre fractal + spacing range ===== -->
    <div v-else-if="styleId === 'color-gosper'" class="space-y-3 border-t border-slate-800 pt-3">
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.gosperOrder') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.order ?? 4)
          }}</span>
        </p>
        <input
          type="range"
          min="1"
          max="6"
          step="1"
          :value="knobs.order ?? 4"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('order', Number((e.target as HTMLInputElement).value))"
        />
        <p class="text-[10px] text-slate-500">{{ t('colorStyles.gosperOrderHint') }}</p>
      </div>
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 3"
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
    </div>

    <!-- ===== Hachures eulériennes couleur: spacing range + angle step + crossed ===== -->
    <div v-else-if="styleId === 'color-eulerian'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 2.5"
        :model-value-max="knobs.spacing_max ?? 6"
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
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('colorStyles.angleStep') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.angle_step ?? 45) }}°</span
          >
        </p>
        <input
          type="range"
          min="0"
          max="90"
          step="5"
          :value="knobs.angle_step ?? 45"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('angle_step', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <label class="flex items-center gap-2 text-[11px] text-slate-300">
        <input
          type="checkbox"
          class="accent-emerald-500"
          :checked="knobs.crossed ?? false"
          @change="(e) => setKnob('crossed', (e.target as HTMLInputElement).checked)"
        />
        {{ t('convert.crossed') }}
      </label>
    </div>

    <!-- ===== TSP optimisé couleur: density range + max points + budget temps ===== -->
    <div v-else-if="styleId === 'color-tsp-opt'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.density_min ?? 0.012"
        :model-value-max="knobs.density_max ?? 0.05"
        :min="0.005"
        :max="0.3"
        :step="0.001"
        @update:model-value-min="(v) => setKnob('density_min', v)"
        @update:model-value-max="(v) => setKnob('density_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.densityRange') }}</span>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.maxPoints') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300">{{
            Math.round(knobs.max_points ?? 4000)
          }}</span>
        </p>
        <input
          type="range"
          min="500"
          max="20000"
          step="500"
          :value="knobs.max_points ?? 8000"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('max_points', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.timeBudgetS') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.time_budget_s ?? 1.5).toFixed(1) }} s</span
          >
        </p>
        <input
          type="range"
          min="0.2"
          max="6"
          step="0.1"
          :value="knobs.time_budget_s ?? 1.5"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('time_budget_s', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Grille couleur: spacing range ===== -->
    <div v-else-if="styleId === 'color-grid'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 3"
        :model-value-max="knobs.spacing_max ?? 7"
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
      </DualRangeSlider>
    </div>

    <!-- ===== Briques couleur: brick size range ===== -->
    <div v-else-if="styleId === 'color-brick'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.cell_min ?? 6"
        :model-value-max="knobs.cell_max ?? 12"
        :min="2"
        :max="30"
        :step="1"
        unit="px"
        @update:model-value-min="(v) => setKnob('cell_min', v)"
        @update:model-value-max="(v) => setKnob('cell_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.cellRange') }}</span>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Pointillés couleur: spacing range + angle step + dash/gap ===== -->
    <div v-else-if="styleId === 'color-dashes'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 3"
        :model-value-max="knobs.spacing_max ?? 6"
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
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('colorStyles.angleStep') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ Math.round(knobs.angle_step ?? 45) }}°</span
          >
        </p>
        <input
          type="range"
          min="0"
          max="90"
          step="5"
          :value="knobs.angle_step ?? 45"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('angle_step', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.dashPx') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.dash_px ?? 3).toFixed(1) }} px</span
          >
        </p>
        <input
          type="range"
          min="0.5"
          max="12"
          step="0.5"
          :value="knobs.dash_px ?? 3"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('dash_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.gapPx') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.gap_px ?? 3).toFixed(1) }} px</span
          >
        </p>
        <input
          type="range"
          min="0.5"
          max="12"
          step="0.5"
          :value="knobs.gap_px ?? 3"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('gap_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <!-- ===== Truchet couleur: cell range ===== -->
    <div v-else-if="styleId === 'color-truchet'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.cell_min ?? 7"
        :model-value-max="knobs.cell_max ?? 14"
        :min="2"
        :max="30"
        :step="1"
        unit="px"
        @update:model-value-min="(v) => setKnob('cell_min', v)"
        @update:model-value-max="(v) => setKnob('cell_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('mono.cellRange') }}</span>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Anneaux couleur: spacing range ===== -->
    <div v-else-if="styleId === 'color-rings'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.spacing_min ?? 4"
        :model-value-max="knobs.spacing_max ?? 8"
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
      </DualRangeSlider>
    </div>

    <!-- ===== Soleil couleur: rays range ===== -->
    <div v-else-if="styleId === 'color-sunburst'" class="space-y-3 border-t border-slate-800 pt-3">
      <DualRangeSlider
        :model-value-min="knobs.rays_min ?? 60"
        :model-value-max="knobs.rays_max ?? 160"
        :min="8"
        :max="360"
        :step="4"
        @update:model-value-min="(v) => setKnob('rays_min', v)"
        @update:model-value-max="(v) => setKnob('rays_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('colorStyles.raysRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('colorStyles.raysRangeHint') }}</p>
        </template>
      </DualRangeSlider>
    </div>

    <!-- ===== Bulles couleur: bubble radius range + gap ===== -->
    <div
      v-else-if="styleId === 'color-circle-pack'"
      class="space-y-3 border-t border-slate-800 pt-3"
    >
      <DualRangeSlider
        :model-value-min="knobs.radius_min ?? 6"
        :model-value-max="knobs.radius_max ?? 11"
        :min="2"
        :max="20"
        :step="0.5"
        unit="px"
        @update:model-value-min="(v) => setKnob('radius_min', v)"
        @update:model-value-max="(v) => setKnob('radius_max', v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t('colorStyles.radiusRange') }}</span>
        </template>
        <template #hint>
          <p class="text-[10px] text-slate-500">{{ t('colorStyles.radiusRangeHint') }}</p>
        </template>
      </DualRangeSlider>
      <div>
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t('convert.gapPx') }}
          <span class="ml-1 font-mono text-[11px] text-slate-300"
            >{{ (knobs.gap_px ?? 0.6).toFixed(1) }} px</span
          >
        </p>
        <input
          type="range"
          min="0"
          max="6"
          step="0.1"
          :value="knobs.gap_px ?? 0.6"
          class="w-full accent-emerald-500"
          @input="(e) => setKnob('gap_px', Number((e.target as HTMLInputElement).value))"
        />
      </div>
    </div>

    <p class="text-[10px] text-slate-500">
      {{ style.descriptionKey ? t(style.descriptionKey) : '' }}
    </p>
  </div>
</template>
