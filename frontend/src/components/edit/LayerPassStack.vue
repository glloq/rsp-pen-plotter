<script setup lang="ts">
import { computed, ref } from 'vue'
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
//   - per-pass visibility toggle (eye) — non-destructive: a hidden
//     pass stays in the emitted stack with ``enabled: false``; the
//     job store strips disabled passes only when building the
//     /rerender payload, so the operator can A/B a stack without
//     losing passes and the state survives remounts + reloads.
//   - style thumbnail per row so the operator recognises an algorithm
//     by glyph + colour without parsing the dropdown label
//   - same curated presets and bottom action row as PassList

const props = defineProps<{
  passes: LayerPass[]
  // Layer identifier — kept for call-site compatibility / debugging;
  // per-pass state now travels on the pass objects themselves
  // (``enabled``) or is keyed by the stable per-row key below.
  layerId?: string
}>()

const emit = defineEmits<{
  (e: 'update', passes: LayerPass[]): void
}>()

const { t } = useI18n()

// ---- Stable per-row keys -------------------------------------------
// LayerPass objects have no id of their own, so we assign one lazily
// via a WeakMap. The store shares pass objects back through props
// (applyLayerPasses keeps references), and every in-component edit
// carries the old object's key onto its replacement — so a row keeps
// its key (and therefore its expanded state and DOM node) across
// option edits, reorders and duplicates. Used both as the draggable
// ``item-key`` and to key the expanded map.
let nextPassKey = 1
const PASS_KEYS = new WeakMap<LayerPass, number>()
function passKey(pass: LayerPass): number {
  let key = PASS_KEYS.get(pass)
  if (key === undefined) {
    key = nextPassKey++
    PASS_KEYS.set(pass, key)
  }
  return key
}
/** Transfer ``from``'s row key onto its replacement object. */
function withKeyOf(from: LayerPass, to: LayerPass): LayerPass {
  PASS_KEYS.set(to, passKey(from))
  return to
}

// Available algorithms in the stack picker — everything in the registry
// except ``direct`` (stacking direct on top is a no-op visually) and the
// hidden duplicates (tsp, grid, …) whose visible counterpart covers them.
const algoChoices = computed(() =>
  Object.values(ALGORITHMS).filter((a) => a.id !== 'direct' && !HIDDEN_ALGORITHMS.has(a.id)),
)

// Per-row expanded toggle for the params form, keyed by the stable row
// key (NOT the index, which shifts on reorder / remove). Default
// collapsed so a tall stack stays scannable.
const expanded = ref<Record<number, boolean>>({})
function toggleExpanded(pass: LayerPass): void {
  const key = passKey(pass)
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}
function isExpanded(pass: LayerPass): boolean {
  return !!expanded.value[passKey(pass)]
}
function hasOptions(algorithm: string): boolean {
  return (getAlgorithm(algorithm)?.schema.length ?? 0) > 0
}

// Per-row visibility toggle — non-destructive. The flag lives on the
// pass itself (``enabled``), so it persists through the store, the
// scene storage and any remount; the backend payload is filtered in
// the job store, never here.
function isHidden(pass: LayerPass): boolean {
  return pass.enabled === false
}
function toggleHidden(index: number): void {
  const pass = props.passes[index]
  if (!pass) return
  const next = [...props.passes]
  next[index] = withKeyOf(pass, { ...pass, enabled: isHidden(pass) })
  pushUpdate(next)
}

// Emit the FULL stack — hidden rows included — so the parent/store
// state always carries every pass. Filtering for the backend happens
// in the job store when the /rerender payload is built.
function pushUpdate(next: LayerPass[]): void {
  emit('update', next)
}

// Two-way binding for vuedraggable. ``draggablePasses`` is the model
// it reads/writes; the setter emits the reordered (full) list.
const draggablePasses = computed<LayerPass[]>({
  get: () => props.passes,
  set: (value) => pushUpdate(value),
})

function onPassAlgorithm(index: number, algorithm: string): void {
  const preset = layerStyles().find((s) => s.defaultAlgorithm === algorithm)
  const pass = props.passes[index]
  if (!pass) return
  const next = [...props.passes]
  next[index] = withKeyOf(pass, {
    ...pass,
    algorithm,
    algorithm_options: {
      ...(preset?.defaultAlgorithmOptions ?? defaultsFor(algorithm)),
    },
  })
  pushUpdate(next)
}

function onOption(index: number, key: string, value: unknown): void {
  const next = [...props.passes]
  const pass = next[index]
  if (!pass) return
  next[index] = withKeyOf(pass, {
    ...pass,
    algorithm_options: { ...pass.algorithm_options, [key]: value },
  })
  pushUpdate(next)
}

function removePass(index: number): void {
  pushUpdate(props.passes.filter((_, i) => i !== index))
}

function duplicatePass(index: number): void {
  const source = props.passes[index]
  if (!source) return
  // Fresh object → fresh row key; per-row state of every other row is
  // untouched because their keys ride on the (unchanged) objects.
  const copy: LayerPass = {
    ...source,
    algorithm_options: { ...source.algorithm_options },
  }
  const next = [...props.passes]
  next.splice(index + 1, 0, copy)
  pushUpdate(next)
}

function addPass(algorithm: AlgorithmId = 'crosshatch'): void {
  const preset = layerStyles().find((s) => s.defaultAlgorithm === algorithm)
  const fresh: LayerPass = {
    algorithm,
    algorithm_options: {
      ...(preset?.defaultAlgorithmOptions ?? defaultsFor(algorithm)),
    },
  }
  pushUpdate([...props.passes, fresh])
  // Auto-expand the freshly added pass so the operator sees the knobs
  // — discoverability win surfaced by the original PassList rewrite.
  expanded.value = { ...expanded.value, [passKey(fresh)]: true }
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
        algorithm_options: { angle_deg: 45, spacing_mm: 1.5, crossed: false },
      },
    ],
  },
  {
    id: 'crossed-hatch',
    labelKey: 'passes.presetCrossedHatch',
    passes: [
      {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: 45, spacing_mm: 1.5, crossed: false },
      },
      {
        algorithm: 'crosshatch',
        algorithm_options: { angle_deg: 135, spacing_mm: 1.5, crossed: false },
      },
    ],
  },
  {
    id: 'contour-stipple',
    labelKey: 'passes.presetContourStipple',
    passes: [
      { algorithm: 'contours', algorithm_options: { spacing_mm: 1.9, max_rings: 12 } },
      { algorithm: 'stippling', algorithm_options: { density: 0.02, dot_radius_mm: 0.19, seed: 0 } },
    ],
  },
]

function applyPreset(preset: PassPreset): void {
  expanded.value = {}
  pushUpdate(
    preset.passes.map((p) => ({
      algorithm: p.algorithm,
      algorithm_options: { ...p.algorithm_options },
    })),
  )
}

function clearAll(): void {
  expanded.value = {}
  pushUpdate([])
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
      :item-key="(pass: LayerPass) => passKey(pass)"
      handle=".pass-handle"
      :animation="150"
      ghost-class="opacity-50"
      tag="div"
      class="space-y-1"
    >
      <template #item="{ element: pass, index: i }: { element: LayerPass; index: number }">
        <div
          class="rounded bg-slate-900 px-1.5 py-1 transition"
          :class="isHidden(pass) ? 'opacity-50' : ''"
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
              :class="isHidden(pass) ? 'text-amber-500' : 'text-slate-300'"
              :title="isHidden(pass) ? t('passes.show') : t('passes.hide')"
              :data-test="`pass-toggle-${i}`"
              @click="toggleHidden(i)"
            >
              {{ isHidden(pass) ? '◌' : '●' }}
            </button>
            <span class="relative inline-flex">
              <StyleThumbnail :algorithm="pass.algorithm" size="sm" />
              <span
                v-if="isHidden(pass)"
                class="pointer-events-none absolute inset-0 flex items-center justify-center text-[14px] font-bold leading-none text-amber-400"
                aria-hidden="true"
                >⊘</span
              >
            </span>
            <select
              :value="pass.algorithm"
              class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-1.5 py-0.5 text-[11px] text-slate-100"
              :class="isHidden(pass) ? 'line-through text-slate-500' : ''"
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
              :class="isExpanded(pass) ? 'text-emerald-300' : ''"
              :title="t('passes.toggleOptions')"
              @click="toggleExpanded(pass)"
            >
              ⚙
            </button>
            <button
              type="button"
              class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
              :title="t('passes.duplicate')"
              :data-test="`pass-duplicate-${i}`"
              @click="duplicatePass(i)"
            >
              ⎘
            </button>
            <button
              type="button"
              class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-rose-300 hover:bg-rose-900/60"
              :title="t('passes.remove')"
              :data-test="`pass-remove-${i}`"
              @click="removePass(i)"
            >
              ✕
            </button>
          </div>

          <!-- Per-pass parameter form — collapsed by default so a tall
               stack stays scannable. Only rendered when the algorithm
               actually has knobs. -->
          <div
            v-if="isExpanded(pass) && hasOptions(pass.algorithm)"
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
