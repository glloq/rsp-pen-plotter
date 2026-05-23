<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getAlgorithms,
  type AlgorithmInfo,
  type LayerInfo,
  type PausePolicy,
} from '../api/client'
import { formatLayerLabel } from '../lib/labels'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const props = defineProps<{ layer: LayerInfo }>()
const store = useJobStore()

const algorithms = ref<AlgorithmInfo[]>([])
onMounted(async () => {
  try { algorithms.value = await getAlgorithms() } catch { /* keep [] */ }
})

// Per-algorithm option schemas: each entry is the set of knobs the
// backend's renderer accepts, plus their defaults. The schema drives
// the inline form rendered below the algorithm selector.
interface AlgoOption {
  key: string
  label: string
  type: 'number' | 'boolean'
  min?: number
  max?: number
  step?: number
}
interface AlgoSpec {
  defaults: Record<string, unknown>
  schema: AlgoOption[]
}
const ALGO_OPTIONS: Record<string, AlgoSpec> = {
  direct: { defaults: {}, schema: [] },
  halftone: {
    defaults: { cell_size_px: 6 },
    schema: [
      { key: 'cell_size_px', label: 'convert.cellSize', type: 'number', min: 1, max: 64, step: 1 },
    ],
  },
  stippling: {
    defaults: { density: 0.02, dot_radius_px: 0.6, seed: 0 },
    schema: [
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'dot_radius_px', label: 'convert.dotRadius', type: 'number', min: 0.1, max: 5, step: 0.1 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
  crosshatch: {
    defaults: { angle_deg: 45, spacing_px: 4, crossed: false },
    schema: [
      { key: 'angle_deg', label: 'convert.angleDeg', type: 'number', min: 0, max: 180, step: 1 },
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'crossed', label: 'convert.crossed', type: 'boolean' },
    ],
  },
  contours: {
    defaults: { spacing_px: 4, max_rings: 20 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'max_rings', label: 'convert.maxRings', type: 'number', min: 1, max: 100, step: 1 },
    ],
  },
  edges: {
    defaults: { stroke_width: 0.8 },
    schema: [
      { key: 'stroke_width', label: 'convert.strokeWidthPx', type: 'number', min: 0.1, max: 5, step: 0.1 },
    ],
  },
  spiral: {
    defaults: { spacing_px: 4, samples_per_turn: 64 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'samples_per_turn', label: 'convert.samplesPerTurn', type: 'number', min: 16, max: 256, step: 1 },
    ],
  },
  scanlines: {
    defaults: { spacing_px: 4, wave_amp_px: 0, wave_period_px: 12 },
    schema: [
      { key: 'spacing_px', label: 'convert.spacing', type: 'number', min: 1, max: 30, step: 0.5 },
      { key: 'wave_amp_px', label: 'convert.waveAmp', type: 'number', min: 0, max: 20, step: 0.5 },
      { key: 'wave_period_px', label: 'convert.wavePeriod', type: 'number', min: 2, max: 50, step: 0.5 },
    ],
  },
  tsp: {
    defaults: { density: 0.02, seed: 0 },
    schema: [
      { key: 'density', label: 'convert.density', type: 'number', min: 0.001, max: 0.5, step: 0.001 },
      { key: 'seed', label: 'convert.seed', type: 'number', min: 0, step: 1 },
    ],
  },
}

// Only bitmap-derived layers (label like ``color-XXXXXX``) can be
// re-rendered with a different algorithm — that's what the /rerender
// cache holds. SVG / DXF / text / document layers come straight from
// the converter as vector groups and have nothing to re-render.
const isBitmapLayer = computed(() => /^color-/.test(props.layer.layer_id))
const currentAlgorithm = computed(
  () => store.layerAlgorithms[props.layer.layer_id]?.algorithm ?? '',
)
const currentAlgoOptions = computed(
  () => store.layerAlgorithms[props.layer.layer_id]?.algorithm_options ?? {},
)
const currentAlgoSpec = computed<AlgoSpec | null>(
  () => (currentAlgorithm.value ? (ALGO_OPTIONS[currentAlgorithm.value] ?? null) : null),
)

async function onAlgorithm(event: Event): Promise<void> {
  const value = (event.target as HTMLSelectElement).value
  if (!value) {
    // "default" — drop the override so the layer rerenders with the
    // initial algorithm baked in at upload time.
    await store.clearLayerAlgorithm(props.layer.layer_id)
    return
  }
  // Seed the option payload with the schema defaults so the very first
  // `/rerender` call already exercises the algorithm with sensible knobs.
  const defaults = { ...(ALGO_OPTIONS[value]?.defaults ?? {}) }
  await store.applyLayerAlgorithm(props.layer.layer_id, value, defaults)
}

async function onAlgoOption(key: string, value: unknown): Promise<void> {
  if (!currentAlgorithm.value) return
  const merged = { ...currentAlgoOptions.value, [key]: value }
  await store.applyLayerAlgorithm(props.layer.layer_id, currentAlgorithm.value, merged)
}

function optionValue(opt: AlgoOption): unknown {
  const stored = currentAlgoOptions.value[opt.key]
  if (stored !== undefined) return stored
  return currentAlgoSpec.value?.defaults[opt.key]
}

const visible = computed({
  get: () => store.isVisible(props.layer.layer_id),
  set: (value: boolean) => store.setVisibility(props.layer.layer_id, value),
})

const label = computed(() => formatLayerLabel(props.layer.layer_id))

const swatchColor = computed(() => label.value.color ?? props.layer.source_color)

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

const penSlots = computed(() => {
  const profile = store.selectedProfile
  const pens = profile?.pens ?? []
  return Array.from({ length: penSlotCount.value }, (_, i) => {
    const pen = pens.find((p) => p.index === i)
    return { index: i, name: pen?.name || `${i}`, color: pen?.color ?? '#94a3b8' }
  })
})

const selectedPen = computed(() =>
  props.layer.target_pen_slot === null
    ? null
    : (penSlots.value.find((p) => p.index === props.layer.target_pen_slot) ?? null),
)

function onPenSlot(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  store.updateLayer(props.layer.layer_id, { target_pen_slot: value === '' ? null : Number(value) })
}

function onSpeed(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  store.updateLayer(props.layer.layer_id, {
    drawing_speed_mm_s: value === '' ? null : Number(value),
  })
}

function onSimplify(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    simplify_tolerance_mm: Number((event.target as HTMLInputElement).value),
  })
}

function onOptimize(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    optimize: (event.target as HTMLInputElement).checked,
  })
}

function onColorLabel(event: Event): void {
  const raw = (event.target as HTMLInputElement).value.trim()
  store.updateLayer(props.layer.layer_id, { color_label: raw || null })
}

function setPause(policy: PausePolicy): void {
  store.updateLayer(props.layer.layer_id, { pause_before: policy })
}

const pauseChoices: Array<{ value: PausePolicy; icon: string; key: string }> = [
  { value: 'auto', icon: '⏸', key: 'layers.pauseAuto' },
  { value: 'always', icon: '✋', key: 'layers.pauseAlways' },
  { value: 'never', icon: '▶', key: 'layers.pauseNever' },
]

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const duration = computed(() => formatDuration(store.layerDurationSeconds(props.layer)))
</script>

<template>
  <div class="rounded border border-slate-700 bg-slate-800 px-3 py-2 space-y-2">
    <div class="flex items-center gap-3">
      <span class="cursor-grab text-slate-500 select-none" :title="t('layers.dragHint')" aria-hidden="true">⠿</span>
      <input v-model="visible" type="checkbox" class="h-4 w-4 accent-emerald-500" />

      <span
        v-if="label.kind === 'image'"
        class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 text-[10px]"
        :title="t('layers.kindImage')"
        aria-hidden="true"
      >🖼</span>
      <span
        v-else-if="label.kind === 'text'"
        class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 font-serif text-xs text-slate-300"
        :title="t('layers.kindText')"
        aria-hidden="true"
      >Aa</span>
      <span
        v-else
        class="h-5 w-5 rounded border border-slate-600 shrink-0"
        :style="{ backgroundColor: swatchColor }"
      />

      <div class="min-w-0 flex-1">
        <p class="truncate text-sm text-slate-200" :class="label.kind === 'color' ? 'font-mono' : ''">
          {{ label.display }}
        </p>
        <p class="text-xs text-slate-500">
          {{ layer.path_count }} {{ t('layers.paths') }} ·
          {{ layer.total_length_mm.toFixed(1) }} mm · {{ duration }}
        </p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <!-- Multi-pen machines: explicit slot assignment. -->
      <label v-if="store.isMultiColor" class="text-slate-400">
        <span class="flex items-center gap-1">
          {{ t('layers.penSlot') }}
          <span
            v-if="selectedPen"
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: selectedPen.color }"
          />
        </span>
        <select
          :value="layer.target_pen_slot ?? ''"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onPenSlot"
        >
          <option value="">{{ t('layers.none') }}</option>
          <option v-for="pen in penSlots" :key="pen.index" :value="pen.index">
            {{ pen.index }} — {{ pen.name }}
          </option>
        </select>
      </label>
      <!-- Mono-pen machines: colour label used in the pause prompt. -->
      <label v-else class="text-slate-400">
        <span class="flex items-center gap-1">
          {{ t('layers.colorLabel') }}
          <span
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: swatchColor }"
          />
        </span>
        <input
          type="text"
          :value="layer.color_label ?? ''"
          :placeholder="layer.source_color"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onColorLabel"
        />
      </label>

      <label class="text-slate-400">
        {{ t('layers.speed') }}
        <input
          type="number"
          min="1"
          :value="layer.drawing_speed_mm_s ?? ''"
          :placeholder="t('layers.default')"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSpeed"
        />
      </label>
      <label class="text-slate-400">
        {{ t('layers.simplify') }}
        <input
          type="number"
          min="0"
          step="0.01"
          :value="layer.simplify_tolerance_mm"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSimplify"
        />
      </label>
      <label class="flex items-end gap-2 text-slate-400">
        <input
          type="checkbox"
          :checked="layer.optimize"
          class="h-4 w-4 accent-emerald-500"
          @change="onOptimize"
        />
        {{ t('layers.optimize') }}
      </label>
    </div>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] text-slate-500">
      <!-- Render algorithm: only meaningful for bitmap-derived layers. -->
      <label v-if="isBitmapLayer" class="flex items-center gap-1.5">
        <span>{{ t('layers.renderAlgorithm') }}</span>
        <select
          :value="currentAlgorithm"
          class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100"
          @change="onAlgorithm"
        >
          <option value="">{{ t('layers.defaultAlgo') }}</option>
          <option v-for="algo in algorithms" :key="algo.name" :value="algo.name">
            {{ algo.name }}
          </option>
        </select>
      </label>

      <div class="flex items-center gap-1.5">
        <span>{{ t('layers.pauseBefore') }}</span>
        <div class="flex overflow-hidden rounded border border-slate-700">
          <button
            v-for="choice in pauseChoices"
            :key="choice.value"
            type="button"
            class="px-2 py-0.5 transition"
            :class="layer.pause_before === choice.value
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
            :title="t(choice.key)"
            @click="setPause(choice.value)"
          >
            <span aria-hidden="true">{{ choice.icon }}</span>
            <span class="ml-1">{{ t(choice.key) }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Per-algorithm settings: appear inline whenever a non-default
         renderer is selected for this layer. The schema is hardcoded to
         match the backend's algorithm signatures. -->
    <div
      v-if="isBitmapLayer && currentAlgoSpec && currentAlgoSpec.schema.length"
      class="rounded border border-slate-700 bg-slate-900/50 p-2"
    >
      <p class="mb-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        {{ t('layers.algoSettings', { algorithm: currentAlgorithm }) }}
      </p>
      <div class="grid grid-cols-2 gap-2 text-[11px]">
        <template v-for="opt in currentAlgoSpec.schema" :key="opt.key">
          <label v-if="opt.type === 'boolean'" class="flex items-center gap-1.5 text-slate-400">
            <input
              type="checkbox"
              :checked="Boolean(optionValue(opt))"
              class="h-3.5 w-3.5 accent-emerald-500"
              @change="(e) => onAlgoOption(opt.key, (e.target as HTMLInputElement).checked)"
            />
            {{ t(opt.label) }}
          </label>
          <label v-else class="block text-slate-400">
            {{ t(opt.label) }}
            <input
              type="number"
              :min="opt.min"
              :max="opt.max"
              :step="opt.step"
              :value="optionValue(opt)"
              class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100"
              @change="(e) => onAlgoOption(opt.key, Number((e.target as HTMLInputElement).value))"
            />
          </label>
        </template>
      </div>
    </div>
  </div>
</template>
