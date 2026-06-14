<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getAlgorithm,
  resolveMasterStyle,
  resolveMulticolorStyle,
} from '../../../data/printRegistry'
import {
  effectiveRangeMin,
  resolveStyleKnobConfig,
  styleKnobDefaults,
  type AngleSetKnob,
  type MasterStyleFamily,
  type RangeKnob,
} from '../../../data/styleKnobs'
import AlgoParamsForm from '../AlgoParamsForm.vue'
import DualRangeSlider from './DualRangeSlider.vue'

// Generic, data-driven renderer for the per-style knob blocks of both
// master-style params cards (mono + multicolour). The per-style UI —
// which knobs, bounds, labels, ordering — lives in
// ``data/styleKnobs.ts``; this component just walks the descriptor list
// and emits ``set(key, value)`` for every edit. The parents own the
// draft writes + the throttled layer propagation, which differ between
// the two pipelines.
//
// Styles without a descriptor entry fall back to the schema-driven
// ``AlgoParamsForm`` (full option set of the style's default algorithm,
// written into ``knobs.algoOverrides``) — same contract the twins had.

const props = defineProps<{
  family: MasterStyleFamily
  styleId: string
  knobs: Record<string, unknown>
  /**
   * Pen tip diameter (mm) of the colour(s) this style draws with, used
   * to floor the physical mark-size knobs (``dot_radius``,
   * ``stroke_width``) — you can't draw thinner than the pen. ``null`` /
   * ``undefined`` (pen width unknown) leaves the descriptor bounds as-is.
   */
  minPenWidthMm?: number | null
}>()

const emit = defineEmits<{ set: [key: string, value: unknown] }>()

const { t } = useI18n()

// Descriptor lookup uses the RAW prop id — mirrors the strict
// ``styleId === '...'`` checks of the pre-refactor twins (legacy-id
// normalisation is the draft's concern, upstream of this card).
const config = computed(() => resolveStyleKnobConfig(props.family, props.styleId))
const defaults = computed(() => styleKnobDefaults(props.family, props.styleId))

// Resolved registry entry — only needed for the generic fallback.
const style = computed(() =>
  props.family === 'mono'
    ? resolveMasterStyle(props.styleId)
    : resolveMulticolorStyle(props.styleId),
)

// ---- Current values (knob store → registry defaults) ----

function num(key: string): number {
  const v = props.knobs[key] ?? defaults.value[key]
  return typeof v === 'number' ? v : 0
}

// Slider lower bound for a range knob, raised to the pen's physical mark
// size when the knob is a dot radius / line width (see ``penFloor``).
function rangeMin(ctl: RangeKnob): number {
  return effectiveRangeMin(ctl, props.minPenWidthMm)
}

// Current value clamped up to the pen floor so the readout and thumb
// never show a thinner mark than the pen can make, even if the stored
// knob predates the pen choice.
function rangeValue(ctl: RangeKnob): number {
  return Math.max(num(ctl.key), rangeMin(ctl))
}

// Persist the floor: when a stored physical knob sits below the pen's
// mark size, raise it so the preview and generated gcode match the
// slider rather than silently drawing at the (clamped-up) tip width.
// Runs off a watcher — never during render — and settles in one pass
// because the emitted value equals the new floor.
watch(
  [config, () => props.minPenWidthMm, () => props.knobs],
  () => {
    for (const ctl of config.value?.controls ?? []) {
      if (ctl.kind !== 'range' || !ctl.penFloor) continue
      const floor = rangeMin(ctl)
      if (num(ctl.key) < floor) emit('set', ctl.key, floor)
    }
  },
  { immediate: true, deep: true },
)

function bool(key: string): boolean {
  const v = props.knobs[key] ?? defaults.value[key]
  return typeof v === 'boolean' ? v : false
}

// Value for the editable numeric input (non-percent range knobs), snapped
// to the descriptor's precision so the field never shows a float tail.
function rangeNumber(ctl: RangeKnob): number {
  const v = rangeValue(ctl)
  return ctl.decimals !== undefined ? Number(v.toFixed(ctl.decimals)) : v
}

// Commit a typed value, clamped to the knob's (pen-floored) bounds.
function onRangeNumber(ctl: RangeKnob, raw: string): void {
  const v = Number(raw)
  if (Number.isNaN(v)) return
  emit('set', ctl.key, Math.min(ctl.max, Math.max(rangeMin(ctl), v)))
}

function rangeDisplay(ctl: RangeKnob): string {
  const v = rangeValue(ctl)
  let text: string
  if (ctl.percent) text = `${Math.round(v * 100)}%`
  else if (ctl.decimals !== undefined) text = v.toFixed(ctl.decimals)
  else text = String(Math.round(v))
  return ctl.unit ? `${text}${ctl.unit}` : text
}

// ---- Angle chip picker (hatch family) ----

function angleValues(ctl: AngleSetKnob): number[] {
  const v = props.knobs[ctl.key] ?? defaults.value[ctl.key]
  return Array.isArray(v) ? (v as number[]) : []
}

function isAngleActive(ctl: AngleSetKnob, angle: number): boolean {
  return angleValues(ctl).includes(angle)
}

function toggleAngle(ctl: AngleSetKnob, angle: number): void {
  const current = [...angleValues(ctl)]
  const idx = current.indexOf(angle)
  if (idx >= 0) {
    // Keep at least one angle so the recipe always has something to draw.
    if (current.length <= 1) return
    current.splice(idx, 1)
  } else {
    if (current.length >= ctl.maxSelected) return
    current.push(angle)
  }
  emit('set', ctl.key, current)
}

// ---- Generic schema-driven fallback (no descriptor entry) ----

const genericAlgoValues = computed<Record<string, unknown>>(() => ({
  ...style.value.defaultAlgorithmOptions,
  ...((props.knobs.algoOverrides as Record<string, unknown> | undefined) ?? {}),
}))

// Hide the fallback card entirely for algorithms without operator
// knobs (e.g. ``direct``) — an empty bordered block reads as a bug.
const genericHasKnobs = computed(
  () => (getAlgorithm(style.value.defaultAlgorithm)?.schema.length ?? 0) > 0,
)

function setAlgoOverride(key: string, value: unknown): void {
  emit('set', 'algoOverrides', {
    ...((props.knobs.algoOverrides as Record<string, unknown> | undefined) ?? {}),
    [key]: value,
  })
}
</script>

<template>
  <!-- Intentionally knob-less styles (flat aplats): placeholder line -->
  <p
    v-if="config?.placeholderKey"
    class="rounded border border-slate-800 bg-slate-900/40 px-2 py-1.5 text-[10px] text-slate-500"
  >
    {{ t(config.placeholderKey) }}
  </p>

  <!-- Descriptor-driven knob block -->
  <div v-else-if="config" class="space-y-3 border-t border-slate-800 pt-3">
    <p v-if="config.introHintKey" class="text-[10px] leading-snug text-slate-500">
      {{ t(config.introHintKey) }}
    </p>

    <template v-for="(ctl, ci) in config.controls" :key="ci">
      <!-- Two-thumb min/max range (lerped dark → light) -->
      <DualRangeSlider
        v-if="ctl.kind === 'dual-range'"
        :model-value-min="num(ctl.keyMin)"
        :model-value-max="num(ctl.keyMax)"
        :min="ctl.min"
        :max="ctl.max"
        :step="ctl.step"
        :unit="ctl.unit"
        @update:model-value-min="(v) => emit('set', ctl.keyMin, v)"
        @update:model-value-max="(v) => emit('set', ctl.keyMax, v)"
      >
        <template #label>
          <span class="uppercase tracking-wider">{{ t(ctl.labelKey) }}</span>
        </template>
        <template v-if="ctl.hintKey" #hint>
          <p class="text-[10px] text-slate-500">{{ t(ctl.hintKey) }}</p>
        </template>
      </DualRangeSlider>

      <!-- Single global slider (+ editable numeric input) -->
      <div v-else-if="ctl.kind === 'range'" class="space-y-1">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[10px] uppercase tracking-wider text-slate-400">
            {{ t(ctl.labelKey) }}
          </p>
          <span v-if="ctl.percent" class="font-mono text-[11px] text-slate-300">{{
            rangeDisplay(ctl)
          }}</span>
          <span v-else class="flex items-center gap-1">
            <input
              type="number"
              :min="rangeMin(ctl)"
              :max="ctl.max"
              :step="ctl.step"
              :value="rangeNumber(ctl)"
              class="w-16 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-100"
              @change="(e) => onRangeNumber(ctl, (e.target as HTMLInputElement).value)"
            />
            <span v-if="ctl.unit" class="font-mono text-[10px] text-slate-500">{{ ctl.unit }}</span>
          </span>
        </div>
        <input
          type="range"
          :min="rangeMin(ctl)"
          :max="ctl.max"
          :step="ctl.step"
          :value="rangeValue(ctl)"
          class="w-full accent-emerald-500"
          @input="(e) => emit('set', ctl.key, Number((e.target as HTMLInputElement).value))"
        />
        <p v-if="ctl.hintKey" class="text-[10px] text-slate-500">{{ t(ctl.hintKey) }}</p>
      </div>

      <!-- Boolean toggle -->
      <label
        v-else-if="ctl.kind === 'checkbox'"
        class="flex items-center gap-2 text-[11px] text-slate-300"
      >
        <input
          type="checkbox"
          class="accent-emerald-500"
          :checked="bool(ctl.key)"
          @change="(e) => emit('set', ctl.key, (e.target as HTMLInputElement).checked)"
        />
        {{ t(ctl.labelKey) }}
      </label>

      <!-- Hatch-angle chip picker -->
      <div v-else-if="ctl.kind === 'angle-set'">
        <p class="text-[10px] uppercase tracking-wider text-slate-400">
          {{ t(ctl.labelKey) }}
        </p>
        <div class="mt-1 flex gap-1">
          <button
            v-for="a in ctl.choices"
            :key="a"
            type="button"
            class="rounded border px-2 py-1 text-[11px] font-mono"
            :class="
              isAngleActive(ctl, a)
                ? 'border-emerald-500 bg-emerald-500/20 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-500'
            "
            @click="toggleAngle(ctl, a)"
          >
            {{ a }}°
          </button>
        </div>
        <p v-if="ctl.hintKey" class="mt-1 text-[10px] text-slate-500">{{ t(ctl.hintKey) }}</p>
      </div>
    </template>
  </div>

  <!-- Generic fallback: schema-driven form for masters without a
       descriptor set (2026-06 tonal/colour batches + any future style
       added to printRegistry without a styleKnobs entry). -->
  <div v-else-if="genericHasKnobs" class="space-y-2 border-t border-slate-800 pt-3">
    <p class="text-[10px] uppercase tracking-wider text-slate-400">
      {{ t('mono.styleSettings') }}
    </p>
    <AlgoParamsForm
      :algorithm="style.defaultAlgorithm"
      :values="genericAlgoValues"
      :min-pen-width-mm="minPenWidthMm"
      @update="setAlgoOverride"
    />
  </div>
</template>
