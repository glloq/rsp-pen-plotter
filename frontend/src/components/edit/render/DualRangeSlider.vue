<script setup lang="ts">
import { computed } from 'vue'

// Two-thumb range slider built from two stacked native ``<input
// type="range">`` controls. Replaces the editor's previous "min/max
// number input pair" pattern with a single horizontal track where the
// operator drags the dark-band endpoint on the left and the light-band
// endpoint on the right.
//
// The two thumbs are kept in order (min <= max) by clamping setters;
// the inputs overlap on the track via ``pointer-events: none`` on the
// track itself with each thumb re-enabling its own pointer events.
// Pure native ``<input>`` keeps keyboard / a11y / focus behaviour for
// free.

const props = withDefaults(defineProps<{
  modelValueMin: number
  modelValueMax: number
  min: number
  max: number
  step?: number
  unit?: string
  format?: (v: number) => string
}>(), {
  step: 1,
  unit: '',
})

const emit = defineEmits<{
  'update:modelValueMin': [value: number]
  'update:modelValueMax': [value: number]
}>()

function setMin(raw: number): void {
  const v = Math.min(raw, props.modelValueMax)
  emit('update:modelValueMin', v)
}

function setMax(raw: number): void {
  const v = Math.max(raw, props.modelValueMin)
  emit('update:modelValueMax', v)
}

function fmt(v: number): string {
  if (props.format) return props.format(v)
  // Choose decimals from the step so a step of 0.001 doesn't show
  // "0.012000000001" while step of 1 doesn't waste space on ".00".
  const decimals = props.step >= 1 ? 0 : (props.step >= 0.1 ? 1 : (props.step >= 0.01 ? 2 : 3))
  return v.toFixed(decimals)
}

const display = computed(() =>
  `${fmt(props.modelValueMin)} → ${fmt(props.modelValueMax)}${props.unit ? ' ' + props.unit : ''}`
)

// Pixel offsets for the highlighted segment between the two thumbs.
const fillStyle = computed(() => {
  const range = props.max - props.min
  if (range <= 0) return { left: '0%', width: '0%' }
  const left = ((props.modelValueMin - props.min) / range) * 100
  const right = ((props.modelValueMax - props.min) / range) * 100
  return { left: `${left}%`, width: `${Math.max(0, right - left)}%` }
})
</script>

<template>
  <div class="space-y-1">
    <div class="flex items-center justify-between text-[10px] text-slate-400">
      <slot name="label" />
      <span class="font-mono text-slate-300">{{ display }}</span>
    </div>
    <div class="dual-range relative h-5">
      <div class="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-slate-700" />
      <div
        class="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-emerald-500"
        :style="fillStyle"
      />
      <input
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="modelValueMin"
        class="dual-range__thumb"
        @input="(e) => setMin(Number((e.target as HTMLInputElement).value))"
      />
      <input
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="modelValueMax"
        class="dual-range__thumb"
        @input="(e) => setMax(Number((e.target as HTMLInputElement).value))"
      />
    </div>
    <slot name="hint" />
  </div>
</template>

<style scoped>
.dual-range__thumb {
  appearance: none;
  -webkit-appearance: none;
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background: transparent;
  pointer-events: none;
  margin: 0;
}
.dual-range__thumb::-webkit-slider-runnable-track {
  background: transparent;
  height: 100%;
}
.dual-range__thumb::-moz-range-track {
  background: transparent;
  height: 100%;
}
.dual-range__thumb::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  pointer-events: auto;
  height: 14px;
  width: 14px;
  border-radius: 9999px;
  background: #10b981;
  border: 2px solid #0f172a;
  cursor: grab;
  margin-top: 0;
  position: relative;
  z-index: 2;
}
.dual-range__thumb::-moz-range-thumb {
  pointer-events: auto;
  height: 14px;
  width: 14px;
  border-radius: 9999px;
  background: #10b981;
  border: 2px solid #0f172a;
  cursor: grab;
}
.dual-range__thumb:focus { outline: none; }
.dual-range__thumb:focus::-webkit-slider-thumb {
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.4);
}
</style>
