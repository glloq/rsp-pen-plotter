<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import draggable from 'vuedraggable'
import { useI18n } from 'vue-i18n'
import type { LayerPass } from '../../stores/job'
import {
  ALGORITHMS,
  HIDDEN_ALGORITHMS,
  defaultsFor,
  getAlgorithm,
  layerStyles,
  type AlgorithmId,
} from '../../data/printRegistry'
import AlgoParamsForm from './AlgoParamsForm.vue'
import StyleThumbnail from './shared/StyleThumbnail.vue'

// Photoshop-style stack of rendering passes for one layer. Replaces
// PassList.vue with:
//   - drag-to-reorder via the same vuedraggable used by LayersSection
//     (handle = ⠿, no more ▲/▼ buttons)
//   - per-pass duplicate button (⎘)
//   - per-pass visibility toggle (eye) — UI-only for now: a hidden
//     pass is not shipped to /rerender, so the operator can A/B a
//     stack without removing passes. The hidden state lives in this
//     component and is dropped on stack changes from upstream.
//   - style thumbnail per row so the operator recognises an algorithm
//     by glyph + colour without parsing the dropdown label
//   - same curated presets and bottom action row as PassList

const props = defineProps<{
  passes: LayerPass[]
  // Layer identifier — used to key the per-pass visibility state in a
  // module-level Map so the operator's hide/show toggles survive
  // navigating away from this layer card and back. Optional so call
  // sites that don't track layer ids (none today) still compile.
  layerId?: string
}>()

const emit = defineEmits<{
  (e: 'update', passes: LayerPass[]): void
}>()

const { t } = useI18n()

// Module-level visibility store, keyed by layer id → {rowIndex: hidden}.
// Lives outside the component so unmount/remount of LayerCard (which
// happens whenever the operator scrolls or switches variants) doesn't
// wipe the operator's hide/show toggles. ``reactive`` so Vue still
// tracks gets/sets through the computed wrapper below.
const HIDDEN_BY_LAYER: Map<string, Record<number, boolean>> = reactive(new Map())

// Available algorithms in the stack picker — everything in the registry
// except ``direct`` (stacking direct on top is a no-op visually) and the
// hidden duplicates (tsp, grid, …) whose visible counterpart covers them.
const algoChoices = computed(() =>
  Object.values(ALGORITHMS).filter((a) => a.id !== 'direct' && !HIDDEN_ALGORITHMS.has(a.id)),
)

// Per-row expanded toggle for the params form. Default collapsed so
// a tall stack stays scannable; the operator opens the row they want
// to tweak.
const expanded = ref<Record<number, boolean>>({})
function toggleExpanded(i: number): void {
  expanded.value = { ...expanded.value, [i]: !expanded.value[i] }
}
function hasOptions(algorithm: string): boolean {
  return (getAlgorithm(algorithm)?.schema.length ?? 0) > 0
}

// Per-row visibility toggle. Hidden passes are filtered out before
// emitting the update — the backend never sees them, but the
// operator can flip them back on without re-picking the algorithm.
// State is keyed by row index, and the whole map is keyed by layer
// id in a module-level store so toggles survive scrolling away from
// this layer card and back (or switching variants). Without this, a
// hidden pass would silently re-appear the moment the operator
// switches layers, because Vue tears down + remounts each card.
const hidden = computed<Record<number, boolean>>({
  get: () => HIDDEN_BY_LAYER.get(props.layerId ?? '__nolayer__') ?? {},
  set: (value) => {
    HIDDEN_BY_LAYER.set(props.layerId ?? '__nolayer__', value)
  },
})
function toggleHidden(i: number): void {
  hidden.value = { ...hidden.value, [i]: !hidden.value[i] }
  pushUpdate(props.passes)
}

// Computed "what we ship to the backend": passes minus the hidden ones.
function visiblePasses(all: LayerPass[]): LayerPass[] {
  return all.filter((_, i) => !hidden.value[i])
}

function pushUpdate(next: LayerPass[]): void {
  emit('update', visiblePasses(next))
}

// Direct passes-array writer that bypasses the hidden filter — used
// for upstream-visible mutations like add/remove/reorder. The hidden
// filter is reapplied on the next emit.
function pushRaw(next: LayerPass[]): void {
  emit(
    'update',
    next.filter((_, i) => !hidden.value[i]),
  )
}

// Two-way binding for vuedraggable. ``draggablePasses`` is the model
// it reads/writes; the setter pipes the reordered list through the
// hidden filter before emitting upstream.
const draggablePasses = computed<LayerPass[]>({
  get: () => props.passes,
  set: (value) => pushRaw(value),
})

function onPassAlgorithm(index: number, algorithm: string): void {
  const preset = layerStyles().find((s) => s.defaultAlgorithm === algorithm)
  const next = [...props.passes]
  next[index] = {
    algorithm,
    algorithm_options: {
      ...(preset?.defaultAlgorithmOptions ?? defaultsFor(algorithm)),
    },
  }
  pushRaw(next)
}

function onOption(index: number, key: string, value: unknown): void {
  const next = [...props.passes]
  const pass = next[index]
  if (!pass) return
  next[index] = {
    algorithm: pass.algorithm,
    algorithm_options: { ...pass.algorithm_options, [key]: value },
  }
  pushRaw(next)
}

function removePass(index: number): void {
  // Drop the matching hidden flag so subsequent rows keep their state.
  const next = { ...hidden.value }
  delete next[index]
  const shifted: Record<number, boolean> = {}
  for (const k of Object.keys(next)) {
    const ki = Number(k)
    if (ki > index) shifted[ki - 1] = next[ki]!
    else shifted[ki] = next[ki]!
  }
  hidden.value = shifted
  pushRaw(props.passes.filter((_, i) => i !== index))
}

function duplicatePass(index: number): void {
  const source = props.passes[index]
  if (!source) return
  const copy: LayerPass = {
    algorithm: source.algorithm,
    algorithm_options: { ...source.algorithm_options },
  }
  const next = [...props.passes]
  next.splice(index + 1, 0, copy)
  pushRaw(next)
}

function addPass(algorithm: AlgorithmId = 'crosshatch'): void {
  const preset = layerStyles().find((s) => s.defaultAlgorithm === algorithm)
  pushRaw([
    ...props.passes,
    {
      algorithm,
      algorithm_options: {
        ...(preset?.defaultAlgorithmOptions ?? defaultsFor(algorithm)),
      },
    },
  ])
  // Auto-expand the freshly added pass so the operator sees the knobs
  // — discoverability win surfaced by the original PassList rewrite.
  expanded.value = { ...expanded.value, [props.passes.length]: true }
}

// Curated multi-pass presets, identical to PassList's — one click
// stacks a recognisable combo without forcing the operator to know
// which algorithm names compose well.
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
      {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: false },
      },
    ],
  },
  {
    id: 'crossed-hatch',
    labelKey: 'passes.presetCrossedHatch',
    passes: [
      {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: 45, spacing_px: 4, crossed: false },
      },
      {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: 135, spacing_px: 4, crossed: false },
      },
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
  hidden.value = {}
  expanded.value = {}
  pushRaw(
    preset.passes.map((p) => ({
      algorithm: p.algorithm,
      algorithm_options: { ...p.algorithm_options },
    })),
  )
}

function clearAll(): void {
  hidden.value = {}
  expanded.value = {}
  pushRaw([])
}
</script>

<template>
  <div class="space-y-2 rounded border border-slate-700 bg-slate-900/40 p-2">
    <div
      class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500"
    >
      <span>{{ t('passes.title') }}</span>
      <span v-if="passes.length" class="text-slate-600">{{ passes.length }}</span>
    </div>

    <!-- Empty state: front-loaded "+ Add" CTA + preset shortcuts so
         the stack feature is discoverable on first contact. -->
    <div
      v-if="!passes.length"
      class="rounded border-2 border-dashed border-emerald-700 bg-emerald-950/20 p-3 text-center"
    >
      <p class="mb-2 text-[11px] leading-snug text-emerald-200">
        {{ t('passes.emptyHint') }}
      </p>
      <div class="flex flex-wrap items-center justify-center gap-1">
        <button
          type="button"
          class="rounded bg-emerald-600 px-3 py-1 text-[11px] font-medium text-white hover:bg-emerald-500"
          @click="addPass()"
        >
          + {{ t('passes.add') }}
        </button>
        <span class="text-[10px] text-slate-500">{{ t('passes.or') }}</span>
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
      </div>
    </div>

    <!-- Existing passes: draggable rows. Each row = drag handle +
         visibility toggle + thumbnail + algo dropdown + options
         toggle + duplicate + delete. The order in the DOM matches
         the plot order (pass 0 plots first, last on top — Photoshop
         layers convention inverted because we plot bottom-up). -->
    <draggable
      v-if="passes.length"
      v-model="draggablePasses"
      item-key="pass-key"
      handle=".pass-handle"
      :animation="150"
      ghost-class="opacity-50"
      tag="div"
      class="space-y-1"
    >
      <template #item="{ element: pass, index: i }: { element: LayerPass; index: number }">
        <div
          class="rounded bg-slate-900 px-1.5 py-1 transition"
          :class="hidden[i] ? 'opacity-50' : ''"
        >
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="pass-handle cursor-grab rounded px-1 py-0.5 text-[12px] text-slate-500 hover:bg-slate-800 hover:text-slate-300 active:cursor-grabbing"
              :title="t('passes.dragHandle')"
              tabindex="-1"
            >
              ⠿
            </button>
            <button
              type="button"
              class="rounded px-1 py-0.5 text-[11px] hover:bg-slate-800"
              :class="hidden[i] ? 'text-amber-500' : 'text-slate-300'"
              :title="hidden[i] ? t('passes.show') : t('passes.hide')"
              @click="toggleHidden(i)"
            >
              {{ hidden[i] ? '◌' : '●' }}
            </button>
            <span class="relative inline-flex">
              <StyleThumbnail :algorithm="pass.algorithm" size="sm" />
              <span
                v-if="hidden[i]"
                class="pointer-events-none absolute inset-0 flex items-center justify-center text-[14px] font-bold leading-none text-amber-400"
                aria-hidden="true"
                >⊘</span
              >
            </span>
            <select
              :value="pass.algorithm"
              class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100"
              :class="hidden[i] ? 'line-through text-slate-500' : ''"
              @change="(e) => onPassAlgorithm(i, (e.target as HTMLSelectElement).value)"
            >
              <option v-for="algo in algoChoices" :key="algo.id" :value="algo.id">
                {{ algo.id }}
              </option>
            </select>
            <button
              v-if="hasOptions(pass.algorithm)"
              type="button"
              class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
              :class="expanded[i] ? 'text-emerald-300' : ''"
              :title="t('passes.toggleOptions')"
              @click="toggleExpanded(i)"
            >
              ⚙
            </button>
            <button
              type="button"
              class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
              :title="t('passes.duplicate')"
              @click="duplicatePass(i)"
            >
              ⎘
            </button>
            <button
              type="button"
              class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-rose-300 hover:bg-rose-900/60"
              :title="t('passes.remove')"
              @click="removePass(i)"
            >
              ✕
            </button>
          </div>

          <!-- Per-pass parameter form — collapsed by default so a tall
               stack stays scannable. Only rendered when the algorithm
               actually has knobs. -->
          <div
            v-if="expanded[i] && hasOptions(pass.algorithm)"
            class="mt-1 ml-12 rounded border border-slate-800 bg-slate-950/60 p-1.5"
          >
            <AlgoParamsForm
              :algorithm="pass.algorithm"
              :values="pass.algorithm_options"
              compact
              @update="(key, value) => onOption(i, key, value)"
            />
          </div>
        </div>
      </template>
    </draggable>

    <!-- Add + presets + clear when at least one pass exists. The
         empty-state above handles the discoverability case. -->
    <div v-if="passes.length" class="flex flex-wrap items-center gap-1">
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
        type="button"
        class="ml-auto rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-400 hover:border-slate-600 hover:text-slate-200"
        @click="clearAll"
      >
        {{ t('passes.clear') }}
      </button>
    </div>
  </div>
</template>
