<script setup lang="ts">
import { computed, useSlots } from 'vue'

// Unified slider control for the editor's right-hand panel. Renders a
// label row (text or ``#label`` slot) with the value on the right, then
// a full-width range slider, then an optional hint. The value on the
// right is an editable ``<input type="number">`` by default so the
// operator can type or paste an exact value instead of only dragging —
// set ``numeric="false"`` for sliders whose readout isn't a plain number
// (e.g. an "off / N levels" display via ``formatValue``).
//
// The component is value-only (``v-model``); callers that need custom
// clamping or side effects bind ``:model-value`` + ``@update:model-value``
// and do the work in their handler (see LevelsCard's black/white clamp).

const props = withDefaults(
  defineProps<{
    modelValue: number
    label?: string
    min: number
    max: number
    step?: number
    /** Unit suffix shown next to the value (e.g. ``mm``, ``px``, ``%``). */
    unit?: string
    /** Decimals for the readout; inferred from ``step`` when omitted. */
    decimals?: number
    hint?: string
    /** Show the editable numeric input (default). When false, a read-only
        mono readout is shown instead (use with ``formatValue``). */
    numeric?: boolean
    disabled?: boolean
    /** Custom read-only readout formatter; only used when ``numeric`` is false. */
    formatValue?: (v: number) => string
  }>(),
  {
    step: 1,
    numeric: true,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const slots = useSlots()

const decimalsResolved = computed(() => {
  if (props.decimals !== undefined) return props.decimals
  const s = String(props.step ?? 1)
  const dot = s.indexOf('.')
  return dot >= 0 ? s.length - dot - 1 : 0
})

// Value snapped to the configured precision for the number input, so the
// field never shows a long binary-float tail (0.30000000000000004).
const numericValue = computed(() => Number(props.modelValue.toFixed(decimalsResolved.value)))

const readout = computed(() => {
  if (props.formatValue) return props.formatValue(props.modelValue)
  const v = props.modelValue.toFixed(decimalsResolved.value)
  return props.unit ? `${v} ${props.unit}` : v
})

function clamp(v: number): number {
  if (Number.isNaN(v)) return props.min
  return Math.min(props.max, Math.max(props.min, v))
}

function onRange(e: Event): void {
  emit('update:modelValue', Number((e.target as HTMLInputElement).value))
}
function onNumber(e: Event): void {
  emit('update:modelValue', clamp(Number((e.target as HTMLInputElement).value)))
}
</script>

<template>
  <div class="space-y-1">
    <div class="flex items-center justify-between gap-2 text-slate-400">
      <span class="flex items-center gap-1">
        <slot name="label">{{ label }}</slot>
      </span>
      <span v-if="numeric" class="flex items-center gap-1">
        <input
          type="number"
          :min="min"
          :max="max"
          :step="step"
          :value="numericValue"
          :disabled="disabled"
          class="w-16 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          @change="onNumber"
        />
        <span v-if="unit" class="font-mono text-[10px] text-slate-500">{{ unit }}</span>
      </span>
      <span v-else class="font-mono text-[10px] text-slate-500">{{ readout }}</span>
    </div>
    <input
      type="range"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      :disabled="disabled"
      class="w-full accent-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
      @input="onRange"
    />
    <p v-if="hint || slots.hint" class="text-[10px] leading-snug text-slate-500">
      <slot name="hint">{{ hint }}</slot>
    </p>
  </div>
</template>
