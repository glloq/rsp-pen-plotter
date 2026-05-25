<script setup lang="ts">
import { computed, inject, onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getAlgorithms,
  type AlgorithmInfo,
  type LayerInfo,
  type PausePolicy,
} from '../api/client'
import { formatLayerLabel } from '../lib/labels'
import { nearestPen } from '../lib/penMatching'
import { useJobStore, type LayerPass } from '../stores/job'
import PrintStylePicker from './edit/PrintStylePicker.vue'
import LayerPassStack from './edit/LayerPassStack.vue'
import AlgoParamsForm from './edit/AlgoParamsForm.vue'
import { defaultsFor, getAlgoSpec } from '../data/algorithmSchemas'
import type { PrintStyle, PrintStyleKind } from '../data/printRegistry'
import { LayerSelectionKey } from '../composables/useLayerSelection'

const { t } = useI18n()
const props = defineProps<{ layer: LayerInfo }>()
const store = useJobStore()

// Bulk selection (provided by LayersSection). May be null when this
// card is rendered outside the layers section (currently doesn't
// happen, but the inject default keeps the file forgiving).
const selection = inject(LayerSelectionKey, null)
const isSelected = computed(() => Boolean(selection?.isSelected(props.layer.layer_id)))

function onHeaderClick(event: MouseEvent): void {
  // Only intercept click for selection if a modifier is held — plain
  // clicks on the header would otherwise eat collapse-toggle / drag
  // affordances. Shift / Ctrl / Cmd are the canonical list-box
  // modifiers, identical to Finder / Explorer / Slack channel lists.
  if (!selection) return
  if (!event.shiftKey && !event.ctrlKey && !event.metaKey) return
  const allIds = store.layers.map((l) => l.layer_id)
  selection.handleClick(props.layer.layer_id, event, allIds)
}

const algorithms = ref<AlgorithmInfo[]>([])
onMounted(async () => {
  try { algorithms.value = await getAlgorithms() } catch { /* keep [] */ }
})

// Only bitmap-derived layers (label like ``color-XXXXXX``) can be
// re-rendered with a different algorithm — that's what the /rerender
// cache holds. SVG / DXF / text / document layers come straight from
// the converter as vector groups and have nothing to re-render.
// We also require the placement's ``rerenderable`` flag to be true:
// a bitmap uploaded before the cache-rehydration feature shipped won't
// have its segmentation options on disk, so /rerender would silently
// 404 even though the layer label looks like a colour cluster.
const isBitmapLayer = computed(() => {
  if (!/^color-/.test(props.layer.layer_id)) return false
  return store.selectedPlacement?.rerenderable !== false
})
const currentAlgorithm = computed(
  () => store.layerAlgorithms[props.layer.layer_id]?.algorithm ?? '',
)
const currentAlgoOptions = computed(
  () => store.layerAlgorithms[props.layer.layer_id]?.algorithm_options ?? {},
)
// Multi-pass stack for this layer (when set). The PrintStylePicker still
// drives the single-style choice; toggling multi-pass mode opens the
// passes editor below and disables the single-style highlight.
const currentPasses = computed<LayerPass[]>(
  () => store.layerAlgorithms[props.layer.layer_id]?.passes ?? [],
)
const isMultiPass = computed(() => currentPasses.value.length > 0)

function onUpdatePasses(passes: LayerPass[]): void {
  store.applyLayerPasses(props.layer.layer_id, passes)
}

// Promote the currently-selected single style to a one-pass stack so
// the operator can start adding more passes without losing the choice.
function enableMultiPass(): void {
  const algo = currentAlgorithm.value || 'crosshatch'
  const opts = { ...currentAlgoOptions.value }
  store.applyLayerPasses(props.layer.layer_id, [
    { algorithm: algo, algorithm_options: opts },
  ])
}

const currentAlgoSpec = computed(() => getAlgoSpec(currentAlgorithm.value))

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
  await store.applyLayerAlgorithm(props.layer.layer_id, value, defaultsFor(value))
}

async function onAlgoOption(key: string, value: unknown): Promise<void> {
  if (!currentAlgorithm.value) return
  const merged = { ...currentAlgoOptions.value, [key]: value }
  await store.applyLayerAlgorithm(props.layer.layer_id, currentAlgorithm.value, merged)
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

// Nearest installed pen to this layer's source colour. Only meaningful
// for bitmap-derived multicolour layers (mono layers always plot in
// the single ink slot the operator picked, so a pen-match warning
// would just be noise). Severity drives the badge colour: green for
// exact / close matches, amber for ``far``, red for ``wrong`` or
// ``none`` (no pen installed).
const installedPenList = computed(() => {
  const pens = store.selectedProfile?.pens ?? []
  return pens
    .filter((p) => (p.installed ?? false) && typeof p.color === 'string')
    .map((p) => ({ index: p.index, color: p.color, installed: true }))
})

const penMatch = computed(() => {
  if (!isBitmapLayer.value) return null
  if (!store.isMultiColor) return null
  return nearestPen(swatchColor.value, installedPenList.value)
})

// True when the operator hasn't already assigned a slot manually AND
// the nearest pen is far enough that the operator probably wants to
// see the warning. Once they pick a slot we stop nagging — the override
// is intentional.
const showPenWarning = computed(() => {
  if (props.layer.target_pen_slot !== null) return false
  const m = penMatch.value
  if (!m) return false
  return m.severity === 'far' || m.severity === 'wrong' || m.severity === 'none'
})

function applyNearestPen(): void {
  const m = penMatch.value
  if (!m || !m.pen) return
  store.updateLayer(props.layer.layer_id, { target_pen_slot: m.pen.index })
}

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

// Print-style picker drives the algorithm + options in one click. The
// "kind" classifies the layer for the picker's thumbnail filter; we
// don't have a schematic detector yet so colour-derived layers are
// treated as image-content while text layers are explicit.
const styleKind = computed<PrintStyleKind>(() =>
  label.value.kind === 'text' ? 'text' : 'image',
)

function onPickStyle(style: PrintStyle): void {
  store.applyLayerAlgorithm(
    props.layer.layer_id,
    style.defaultAlgorithm,
    { ...style.defaultAlgorithmOptions },
  )
}

function onResetStyle(): void {
  store.clearLayerAlgorithm(props.layer.layer_id)
}

// Toggle to expose the schema-driven advanced form behind the picker.
const showAdvanced = ref(false)
// Collapse the whole card body so a many-layer placement (e.g. 8-colour
// segmentation) is scannable. The header — visibility checkbox, swatch,
// label, path stats — stays visible so the layer can still be
// reordered and toggled on/off while collapsed.
const collapsed = ref(false)

// LayersSection broadcasts an "expand all" / "collapse all" signal via
// provide; honour it whenever it flips so the bulk toggle takes effect
// without overriding the per-card toggle the rest of the time.
const sectionCollapseAll = inject<Ref<boolean | null>>(
  'layersCollapseAll',
  ref<boolean | null>(null),
)
watch(sectionCollapseAll, (value) => {
  if (value === null) return
  collapsed.value = value
})

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const duration = computed(() => formatDuration(store.layerDurationSeconds(props.layer)))
</script>

<template>
  <div
    class="rounded border bg-slate-800 px-3 py-2 space-y-2 transition"
    :class="isSelected
      ? 'border-emerald-500 ring-2 ring-emerald-500 ring-offset-2 ring-offset-slate-900'
      : 'border-slate-700'"
  >
    <div
      class="flex items-center gap-3"
      @click="onHeaderClick"
    >
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
        <p class="flex items-center gap-1.5 truncate text-sm text-slate-200" :class="label.kind === 'color' ? 'font-mono' : ''">
          <span class="truncate">{{ label.display }}</span>
          <span
            v-if="isMultiPass"
            class="shrink-0 rounded-sm border border-emerald-700 bg-emerald-950/60 px-1 py-px text-[9px] font-semibold tracking-wider text-emerald-300"
            :title="t('passes.badgeHint')"
          >×{{ currentPasses.length }}</span>
        </p>
        <p class="text-xs text-slate-500">
          {{ layer.path_count }} {{ t('layers.paths') }} ·
          {{ layer.total_length_mm.toFixed(1) }} mm · {{ duration }}
        </p>
      </div>
      <button
        type="button"
        class="shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-[11px] text-slate-200 hover:bg-slate-600"
        :title="collapsed ? t('layers.expand') : t('layers.collapse')"
        :aria-expanded="!collapsed"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? '▸' : '▾' }}
      </button>
    </div>

    <div v-if="!collapsed" class="grid grid-cols-2 gap-2 text-xs">
      <!-- Multi-pen machines: explicit slot assignment. -->
      <label v-if="store.isMultiColor" class="text-slate-400">
        <span class="flex items-center gap-1">
          {{ t('layers.penSlot') }}
          <span
            v-if="selectedPen"
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: selectedPen.color }"
          />
          <!-- Nearest-pen badge: shown only when no slot is assigned
               yet and the closest installed pen is far enough from the
               source colour to deserve attention. Click to auto-assign
               the suggested slot. ``exact``/``close`` matches stay
               silent; we don't want to nag for matches the operator
               wouldn't second-guess. -->
          <button
            v-if="penMatch && penMatch.severity !== 'none' && layer.target_pen_slot === null"
            type="button"
            class="inline-flex items-center gap-1 rounded border px-1 py-px text-[9px] font-mono transition"
            :class="penMatch.severity === 'far'
              ? 'border-amber-700 bg-amber-950/40 text-amber-200 hover:bg-amber-950'
              : penMatch.severity === 'wrong'
                ? 'border-red-700 bg-red-950/40 text-red-200 hover:bg-red-950'
                : 'border-emerald-700 bg-emerald-950/40 text-emerald-200 hover:bg-emerald-950'"
            :title="t('layers.nearestPenHint', {
              slot: penMatch.pen?.index ?? '?',
              color: penMatch.pen?.color ?? '',
              distance: Math.round(penMatch.distance),
            })"
            @click="applyNearestPen"
          >
            <span
              v-if="penMatch.pen"
              class="inline-block h-2 w-2 rounded-full border border-slate-600"
              :style="{ backgroundColor: penMatch.pen.color }"
            />
            <span>≈ #{{ penMatch.pen?.index ?? '?' }}</span>
          </button>
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
        <p
          v-if="showPenWarning && penMatch && penMatch.pen"
          class="mt-0.5 text-[10px] text-amber-300"
        >
          {{ t('layers.penWarning', {
            color: swatchColor,
            slot: penMatch.pen.index,
            penColor: penMatch.pen.color,
          }) }}
        </p>
        <p
          v-else-if="showPenWarning && penMatch && !penMatch.pen"
          class="mt-0.5 text-[10px] text-red-300"
        >
          {{ t('layers.penWarningNone') }}
        </p>
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

    <!-- Print-style picker: tile grid for bitmap-derived layers. The
         schema-driven advanced form below is gated behind "Advanced".
         Multi-pass mode lifts the layer into a stacked-algorithms editor
         so the same colour can be drawn with several visual effects in
         one ink. -->
    <div v-if="!collapsed && isBitmapLayer" class="space-y-1.5">
      <div class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
        <span>{{ t('layers.printStyle') }}</span>
        <div class="flex items-center gap-1">
          <button
            v-if="!isMultiPass"
            type="button"
            class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-emerald-600 hover:text-emerald-200"
            :title="t('passes.enableHint')"
            @click="enableMultiPass"
          >
            + {{ t('passes.enable') }}
          </button>
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
            @click="showAdvanced = !showAdvanced"
          >
            {{ showAdvanced ? t('layers.advancedHide') : t('layers.advancedShow') }}
          </button>
        </div>
      </div>

      <!-- Single-style picker: hidden while multi-pass is active so the
           operator isn't editing two sources of truth at once. -->
      <PrintStylePicker
        v-if="!isMultiPass"
        :kind="styleKind"
        :current-algorithm="currentAlgorithm"
        @select="onPickStyle"
        @reset="onResetStyle"
      />

      <!-- Multi-pass stack: ordered list of algorithms drawn against the
           same colour mask. Drag the ⠿ handle to reorder; the first
           pass plots first, the last on top. -->
      <LayerPassStack
        v-else
        :passes="currentPasses"
        :layer-id="props.layer.layer_id"
        @update="onUpdatePasses"
      />
    </div>

    <div v-if="!collapsed" class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] text-slate-500">
      <!-- Power-user algorithm dropdown stays available for non-bitmap
           layers (no print-style picker) and behind "Advanced" otherwise. -->
      <label v-if="isBitmapLayer && showAdvanced" class="flex items-center gap-1.5">
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

    <!-- Per-algorithm settings: schema-driven inline form, shared with
         PassList so the same knobs appear wherever an algorithm is
         editable. Hidden unless the user opens "Advanced" AND the
         selected algorithm actually has options. -->
    <div
      v-if="!collapsed && isBitmapLayer && !isMultiPass && showAdvanced && currentAlgoSpec && currentAlgoSpec.schema.length"
      class="rounded border border-slate-700 bg-slate-900/50 p-2"
    >
      <p class="mb-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        {{ t('layers.algoSettings', { algorithm: currentAlgorithm }) }}
      </p>
      <AlgoParamsForm
        :algorithm="currentAlgorithm"
        :values="currentAlgoOptions"
        @update="onAlgoOption"
      />
    </div>
  </div>
</template>
