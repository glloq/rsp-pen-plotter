<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LayerPass } from '../../stores/job'
import { PRINT_STYLES, type PrintStyle } from '../../data/printStyles'
import { defaultsFor, getAlgoSpec } from '../../data/algorithmSchemas'
import AlgoParamsForm from './AlgoParamsForm.vue'

// Multi-pass editor: a single colour can be drawn as the stack of
// several algorithms (e.g. contours outline + crosshatch fill) so the
// operator gets the visual effect of multiple pens without changing
// inks. The list is order-sensitive: pass index 0 plots first, the
// last pass plots on top. Each pass has its own algorithm options
// (angle, spacing, density, …) editable in a per-row dropdown.

const props = defineProps<{
  passes: LayerPass[]
}>()

const emit = defineEmits<{
  (e: 'update', passes: LayerPass[]): void
}>()

const { t } = useI18n()

// Algorithms available as a pass — same catalogue as the single-style
// picker so the UI vocabulary stays consistent. ``direct`` is excluded
// because stacking it on top of another pass is a no-op visually.
const algoChoices = computed(() => PRINT_STYLES.filter((s) => s.algorithm !== 'direct'))

function styleByAlgorithm(algo: string): PrintStyle | undefined {
  return PRINT_STYLES.find((s) => s.algorithm === algo)
}

// Per-row "expanded" toggle for the schema-driven params form. Default
// is collapsed so a stack of 4 passes stays compact; the operator opens
// the one they want to tweak.
const expanded = ref<Record<number, boolean>>({})
function toggleExpanded(i: number): void {
  expanded.value = { ...expanded.value, [i]: !expanded.value[i] }
}
function hasOptions(algorithm: string): boolean {
  return (getAlgoSpec(algorithm)?.schema.length ?? 0) > 0
}

function onPassAlgorithm(index: number, algorithm: string): void {
  const preset = styleByAlgorithm(algorithm)
  const next = [...props.passes]
  next[index] = {
    algorithm,
    // Reset options to the preset defaults (falling back to the
    // schema defaults if no preset exists) whenever the algorithm
    // changes — the previous algo's option keys would be ignored.
    algorithm_options: { ...(preset?.algorithm_options ?? defaultsFor(algorithm)) },
  }
  emit('update', next)
}

function onOption(index: number, key: string, value: unknown): void {
  const next = [...props.passes]
  const pass = next[index]
  if (!pass) return
  next[index] = {
    algorithm: pass.algorithm,
    algorithm_options: { ...pass.algorithm_options, [key]: value },
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
    { algorithm, algorithm_options: { ...(preset?.algorithm_options ?? defaultsFor(algorithm)) } },
  ])
  // Auto-expand the freshly added pass so the operator sees there are
  // knobs to tweak (was a discoverability gap before).
  expanded.value = { ...expanded.value, [props.passes.length]: true }
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
  expanded.value = {}
}

function clearAll(): void {
  emit('update', [])
  expanded.value = {}
}
</script>

<template>
  <div class="space-y-2 rounded border border-slate-700 bg-slate-900/40 p-2">
    <div class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
      <span>{{ t('passes.title') }}</span>
      <span v-if="passes.length" class="text-slate-600">{{ passes.length }}</span>
    </div>

    <!-- Empty state: front-loaded "+ Add" CTA + preset shortcuts so the
         multi-pass feature is discoverable on first contact (the small
         "+ Add" button next to the presets used to hide under noise). -->
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

    <!-- Existing passes: each row = algo dropdown + reorder + delete +
         expand toggle. The schema-driven params form drops in under the
         row when expanded so the operator can fine-tune the pass
         in-line without navigating away. -->
    <div v-if="passes.length" class="space-y-1">
      <div
        v-for="(pass, i) in passes"
        :key="i"
        class="rounded bg-slate-900 px-1.5 py-1"
      >
        <div class="flex items-center gap-1">
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
            v-if="hasOptions(pass.algorithm)"
            type="button"
            class="rounded bg-slate-800 px-1 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
            :class="expanded[i] ? 'text-emerald-300' : ''"
            :title="t('passes.toggleOptions')"
            @click="toggleExpanded(i)"
          >⚙</button>
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

        <!-- Per-pass parameter form: collapsed by default so a tall
             stack stays scannable. Only rendered for algorithms that
             actually have options (``direct`` has none). -->
        <div
          v-if="expanded[i] && hasOptions(pass.algorithm)"
          class="mt-1 ml-5 rounded border border-slate-800 bg-slate-950/60 p-1.5"
        >
          <AlgoParamsForm
            :algorithm="pass.algorithm"
            :values="pass.algorithm_options"
            compact
            @update="(key, value) => onOption(i, key, value)"
          />
        </div>
      </div>
    </div>

    <!-- Add + presets + clear (when at least one pass exists). The
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
