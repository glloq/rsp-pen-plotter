<script setup lang="ts">
// LayerCard orchestrator (L10 #4 finalize).
//
// Post-split this component is a thin wiring layer:
//   - drives ``useLayerCardState`` for all the per-layer derived
//     state + event handlers (visibility, pen slot, speed, simplify,
//     algorithm, multi-pass, pen-match)
//   - composes ``<LayerCardSummary>`` for the always-visible header
//   - keeps the inline body (settings grid + print-style picker +
//     algorithm dropdown + algo params form) here because splitting
//     it would require ~30 prop / emit declarations for almost no
//     structural benefit — every nested form already binds directly
//     against composable refs / handlers
//
// The composable owns the heavy logic (~250 LOC moved out), the
// summary sub-component owns the visually independent header row,
// and this file is left as the template that wires them together.

import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AlgorithmInfo, AlgorithmKind, ColorAssignment, LayerInfo } from '../api/client'
import { resolveEffectivePalette } from '../lib/effectivePalette'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { usePaletteSourceStore } from '../stores/paletteSource'
import { useLayerCardState } from '../composables/useLayerCardState'
import AssignedColorPicker from './edit/AssignedColorPicker.vue'
import LayerCardSummary from './LayerCardSummary.vue'
import PrintStylePicker from './edit/PrintStylePicker.vue'
import LayerPassStack from './edit/LayerPassStack.vue'
import AlgoParamsForm from './edit/AlgoParamsForm.vue'

const { t } = useI18n()
const props = defineProps<{ layer: LayerInfo }>()
const store = useJobStore()

const layerRef = computed(() => props.layer)

const {
  visible,
  showAdvanced,
  collapsed,
  algorithms,
  isSelected,
  isBitmapLayer,
  currentAlgorithm,
  currentAlgoOptions,
  currentPasses,
  isMultiPass,
  currentAlgoSpec,
  label,
  swatchColor,
  penSlots,
  selectedPen,
  penMatch,
  showPenWarning,
  styleKind,
  duration,
  pauseChoices,
  onHeaderClick,
  onUpdatePasses,
  enableMultiPass,
  onAlgorithm,
  onAlgoOption,
  applyNearestPen,
  onPenSlot,
  onSpeed,
  onSimplify,
  onOptimize,
  onOpacity,
  onColorLabel,
  setPause,
  onPickStyle,
  onResetStyle,
} = useLayerCardState(layerRef)

// Effective palette for the per-layer colour picker. Same resolution
// rule as ``StyleTab`` — installed pens, the available-colours
// inventory, or the union of both, driven by the operator's
// ``palette_source`` setting. Recomputes when any input changes so the
// picker swatches always mirror the Plotter > Couleurs tab.
const paletteSource = usePaletteSourceStore()
const availableColorsStore = useAvailableColorsStore()

onMounted(() => {
  if (!paletteSource.loaded) void paletteSource.refresh()
  if (!availableColorsStore.loaded) void availableColorsStore.refresh()
})

const installedPenColors = computed<string[]>(() => {
  const pens = store.selectedProfile?.pens ?? []
  return pens.filter((p) => p.installed && p.color).map((p) => p.color)
})

const availableHexes = computed<string[]>(() => availableColorsStore.ordered.map((c) => c.hex))

const effectivePalette = computed<string[]>(() =>
  resolveEffectivePalette(paletteSource.source, installedPenColors.value, availableHexes.value),
)

function onColorPick(payload: { hex: string; assignment: ColorAssignment }): void {
  store.updateLayer(props.layer.layer_id, {
    assigned_color_hex: payload.hex,
    color_assignment: payload.assignment,
  })
}

function onColorReset(payload: { hex: string | null }): void {
  store.updateLayer(props.layer.layer_id, {
    assigned_color_hex: payload.hex,
    color_assignment: 'auto',
  })
}

// Group the flat algorithm list by family (fill / lines / mono_stroke)
// so the advanced dropdown surfaces an organised picker the wiki
// promises ("full algorithm grid grouped by family"). Each kind maps
// to one ``<optgroup>``; unknown kinds fall into "other" so a future
// backend addition doesn't disappear.
const ALGORITHM_KIND_ORDER: AlgorithmKind[] = ['fill', 'lines', 'mono_stroke']
const algorithmsByKind = computed<Array<{ kind: string; algos: AlgorithmInfo[] }>>(() => {
  const buckets = new Map<string, AlgorithmInfo[]>()
  for (const algo of algorithms.value) {
    // Hidden = backend-flagged duplicate (tsp, grid, …). Keep it only
    // when this layer already uses it, so the select still shows the
    // persisted value instead of a blank.
    if (algo.hidden && algo.name !== currentAlgorithm.value) continue
    const key = (algo.kind as string) ?? 'other'
    const list = buckets.get(key) ?? []
    list.push(algo)
    buckets.set(key, list)
  }
  const ordered: Array<{ kind: string; algos: AlgorithmInfo[] }> = ALGORITHM_KIND_ORDER.filter(
    (k) => buckets.has(k),
  ).map((k) => ({
    kind: k as string,
    algos: buckets.get(k)!.sort((a, b) => a.name.localeCompare(b.name)),
  }))
  for (const [k, list] of buckets) {
    if (!ALGORITHM_KIND_ORDER.includes(k as AlgorithmKind)) {
      ordered.push({ kind: k, algos: list.sort((a, b) => a.name.localeCompare(b.name)) })
    }
  }
  return ordered
})
</script>

<template>
  <div
    :data-layer-card="layer.layer_id"
    class="rounded border bg-slate-800 px-3 py-2 space-y-2 transition"
    :class="
      isSelected
        ? 'border-emerald-500 ring-2 ring-emerald-500 ring-offset-2 ring-offset-slate-900'
        : 'border-slate-700'
    "
  >
    <LayerCardSummary
      :layer="layer"
      :label="label"
      :swatch-color="swatchColor"
      :is-multi-pass="isMultiPass"
      :pass-count="currentPasses.length"
      :duration="duration"
      :collapsed="collapsed"
      :visible="visible"
      @header-click="onHeaderClick"
      @update:collapsed="(v) => (collapsed = v)"
      @update:visible="(v) => (visible = v)"
    />

    <div v-if="!collapsed" class="space-y-3">
      <!-- ============================ COULEUR & STYLO ===================
           Which ink draws this layer and, on multi-pen machines, which
           carousel slot carries it. Grouped first because it answers the
           operator's primary question ("what colour is this?") before
           any path-level tuning. -->
      <section class="space-y-2">
        <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          {{ t('layers.sectionColor') }}
        </p>
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
                :class="
                  penMatch.severity === 'far'
                    ? 'border-amber-700 bg-amber-950/40 text-amber-200 hover:bg-amber-950'
                    : penMatch.severity === 'wrong'
                      ? 'border-red-700 bg-red-950/40 text-red-200 hover:bg-red-950'
                      : 'border-emerald-700 bg-emerald-950/40 text-emerald-200 hover:bg-emerald-950'
                "
                :title="
                  t('layers.nearestPenHint', {
                    slot: penMatch.pen?.index ?? '?',
                    color: penMatch.pen?.color ?? '',
                    distance: Math.round(penMatch.distance),
                  })
                "
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
              {{
                t('layers.penWarning', {
                  color: swatchColor,
                  slot: penMatch.pen.index,
                  penColor: penMatch.pen.color,
                })
              }}
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
        </div>

        <!-- Per-layer colour assignment: shows the snapped ink + lets the
             operator override from the active palette pool. -->
        <AssignedColorPicker
          :layer="layer"
          :effective-palette="effectivePalette"
          @pick="onColorPick"
          @reset="onColorReset"
        />
      </section>

      <!-- ============================ TRACÉ =============================
           Path-level tuning that changes how the pen physically draws
           this layer: drawing speed, curve simplification, travel
           optimisation, preview opacity and the pen-change pause. -->
      <section class="space-y-2 border-t border-slate-700/60 pt-2.5">
        <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          {{ t('layers.sectionPath') }}
        </p>
        <div class="grid grid-cols-2 gap-2 text-xs">
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
          <!-- Opacity slider (preview only): 100 = solid, lower fades the
           layer to preview dilute-ink / watercolor passes. Persists on
           the placement via ``updateLayer`` but the G-code generator
           ignores it — it's a visual cue, not a hardware setting. -->
          <label class="col-span-2 text-slate-400">
            <span class="flex items-center gap-1">
              {{ t('layers.opacity') }}
              <span class="font-mono text-[10px] text-slate-500"
                >{{ layer.opacity_percent ?? 100 }}%</span
              >
            </span>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              :value="layer.opacity_percent ?? 100"
              class="mt-0.5 w-full accent-emerald-500"
              :data-test="`layer-opacity-${layer.layer_id}`"
              @input="onOpacity"
            />
          </label>
        </div>

        <!-- Pen-change pause: how the run behaves right before this
             colour is drawn (auto / always / never). -->
        <div class="flex items-center gap-1.5 text-[10px] text-slate-500">
          <span>{{ t('layers.pauseBefore') }}</span>
          <div class="flex overflow-hidden rounded border border-slate-700">
            <button
              v-for="choice in pauseChoices"
              :key="choice.value"
              type="button"
              class="px-2 py-0.5 transition"
              :class="
                layer.pause_before === choice.value
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              "
              :title="t(choice.key)"
              @click="setPause(choice.value)"
            >
              <span aria-hidden="true">{{ choice.icon }}</span>
              <span class="ml-1">{{ t(choice.key) }}</span>
            </button>
          </div>
        </div>
      </section>

      <!-- ============================ RENDU =============================
           How the source pixels become strokes for this layer: the
           print-style tile grid, optional multi-pass stack, and the
           power-user algorithm picker + its schema-driven knobs. Bitmap
           layers only — vector / text layers keep their source paths. -->
      <section v-if="isBitmapLayer" class="space-y-1.5 border-t border-slate-700/60 pt-2.5">
        <div
          class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500"
        >
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
          :layer-id="layer.layer_id"
          @update="onUpdatePasses"
        />
        <!-- Power-user algorithm picker, grouped by family (fill / lines /
           mono_stroke). Behind "Advanced" — the tile grid above already
           covers the common styles; this is the escape hatch for an
           operator hunting a specific algorithm. -->
        <label v-if="showAdvanced" class="flex items-center gap-1.5 text-[10px] text-slate-500">
          <span>{{ t('layers.renderAlgorithm') }}</span>
          <select
            :value="currentAlgorithm"
            class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100"
            @change="onAlgorithm"
          >
            <option value="">{{ t('layers.defaultAlgo') }}</option>
            <optgroup
              v-for="group in algorithmsByKind"
              :key="group.kind"
              :label="t(`layers.algorithmKind.${group.kind}`, group.kind)"
            >
              <option v-for="algo in group.algos" :key="algo.name" :value="algo.name">
                {{ algo.name }}
              </option>
            </optgroup>
          </select>
        </label>

        <!-- Per-algorithm settings: schema-driven inline form, shared
             with PassList so the same knobs appear wherever an algorithm
             is editable. Hidden unless "Advanced" is open AND the
             selected algorithm actually has options. -->
        <div
          v-if="!isMultiPass && showAdvanced && currentAlgoSpec && currentAlgoSpec.schema.length"
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
      </section>
    </div>
  </div>
</template>
