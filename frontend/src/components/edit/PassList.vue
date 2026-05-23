<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LayerPass } from '../../stores/job'
import { PRINT_STYLES, type PrintStyle } from '../../data/printStyles'

// Multi-pass editor: a single colour can be drawn as the stack of
// several algorithms (e.g. contours outline + crosshatch fill) so the
// operator gets the visual effect of multiple pens without changing
// inks. The list is order-sensitive: pass index 0 plots first, the
// last pass plots on top.

const props = defineProps<{
  passes: LayerPass[]
}>()

const emit = defineEmits<{
  (e: 'update', passes: LayerPass[]): void
}>()

const { t } = useI18n()

// Algorithms available as a pass — same catalogue as the single-style
// picker so the UI vocabulary stays consistent. We surface a flat
// dropdown rather than the tile grid here since each pass is one row.
const algoChoices = computed(() => PRINT_STYLES.filter((s) => s.algorithm !== 'direct'))

function styleByAlgorithm(algo: string): PrintStyle | undefined {
  return PRINT_STYLES.find((s) => s.algorithm === algo)
}

function onPassAlgorithm(index: number, algorithm: string): void {
  const preset = styleByAlgorithm(algorithm)
  const next = [...props.passes]
  next[index] = {
    algorithm,
    // Reset options to the preset defaults whenever the algorithm
    // changes — the previous algo's option keys would be ignored.
    algorithm_options: { ...(preset?.algorithm_options ?? {}) },
  }
  emit('update', next)
}

function removePass(index: number): void {
  emit('update', props.passes.filter((_, i) => i !== index))
}

function movePass(index: number, direction: -1 | 1): void {
  const target = index + direction
  if (target < 0 || target >= props.passes.length) return
  const next = [...props.passes]
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved!)
  emit('update', next)
}

function addPass(algorithm = 'crosshatch'): void {
  const preset = styleByAlgorithm(algorithm)
  emit('update', [
    ...props.passes,
    { algorithm, algorithm_options: { ...(preset?.algorithm_options ?? {}) } },
  ])
}

// Curated multi-pass presets: one click stacks a recognisable combo.
interface PassPreset {
  id: string
  labelKey: string
  passes: LayerPass[]
}

const passPresets: PassPreset[] = [
  {
    id: 'outline-fill',
    labelKey: 'passes.presetOutlineFill',
    passes: [
      { algorithm: 'edges', algorithm_options: { stroke_width: 0.8 } },
      { algorithm: 'crosshatch', algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: false } },
    ],
  },
  {
    id: 'crossed-hatch',
    labelKey: 'passes.presetCrossedHatch',
    passes: [
      { algorithm: 'crosshatch', algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: false } },
      { algorithm: 'crosshatch', algorithm_options: { angle_deg: 135, spacing_px: 4, crossed: false } },
    ],
  },
  {
    id: 'contour-stipple',
    labelKey: 'passes.presetContourStipple',
    passes: [
      { algorithm: 'contours', algorithm_options: { spacing_px: 5, max_rings: 12 } },
      { algorithm: 'stippling', algorithm_options: { density: 0.02, dot_radius_px: 0.5, seed: 0 } },
    ],
  },
]

function applyPreset(preset: PassPreset): void {
  emit('update', preset.passes.map((p) => ({
    algorithm: p.algorithm,
    algorithm_options: { ...p.algorithm_options },
  })))
}

function clearAll(): void {
  emit('update', [])
}
</script>

<template>
  <div class="space-y-1.5 rounded border border-slate-700 bg-slate-900/40 p-2">
    <div class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
      <span>{{ t('passes.title') }}</span>
      <span v-if="passes.length" class="text-slate-600">{{ passes.length }}</span>
    </div>

    <!-- Existing passes: each row = algo dropdown + reorder + delete. -->
    <div v-if="passes.length" class="space-y-1">
      <div
        v-for="(pass, i) in passes"
        :key="i"
        class="flex items-center gap-1 rounded bg-slate-900 px-1.5 py-1"
      >
        <span class="w-4 shrink-0 text-center font-mono text-[10px] text-slate-500">{{ i + 1 }}</span>
        <select
          :value="pass.algorithm"
          class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100"
          @change="(e) => onPassAlgorithm(i, (e.target as HTMLSelectElement).value)"
        >
          <option v-for="style in algoChoices" :key="style.id" :value="style.algorithm">
            {{ t(style.labelKey) }}
          </option>
        </select>
        <button
          type="button"
          class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700 disabled:opacity-30"
          :disabled="i === 0"
          :title="t('passes.moveUp')"
          @click="movePass(i, -1)"
        >▲</button>
        <button
          type="button"
          class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700 disabled:opacity-30"
          :disabled="i === passes.length - 1"
          :title="t('passes.moveDown')"
          @click="movePass(i, 1)"
        >▼</button>
        <button
          type="button"
          class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-rose-300 hover:bg-rose-900/60"
          :title="t('passes.remove')"
          @click="removePass(i)"
        >✕</button>
      </div>
    </div>

    <p v-else class="text-[10px] leading-snug text-slate-500">
      {{ t('passes.emptyHint') }}
    </p>

    <!-- Add + curated presets -->
    <div class="flex flex-wrap items-center gap-1">
      <button
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-200 hover:border-slate-600"
        @click="addPass()"
      >
        + {{ t('passes.add') }}
      </button>
      <button
        v-for="preset in passPresets"
        :key="preset.id"
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-emerald-600 hover:text-emerald-200"
        :title="t('passes.applyPreset')"
        @click="applyPreset(preset)"
      >
        {{ t(preset.labelKey) }}
      </button>
      <button
        v-if="passes.length"
        type="button"
        class="ml-auto rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-400 hover:border-slate-600 hover:text-slate-200"
        @click="clearAll"
      >
        {{ t('passes.clear') }}
      </button>
    </div>
  </div>
</template>
