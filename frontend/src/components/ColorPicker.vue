<script setup lang="ts">
// Modal-based colour picker — replaces the native ``<input type="color">``
// which doesn't open reliably on every browser / kiosk runtime.
//
// The component renders just a swatch button; clicking it opens a modal
// overlay with an HSV saturation/value plane, a hue strip, a hex input
// and a row of preset swatches. The selection is only committed when
// the operator clicks "Confirm" so a stray drag doesn't mutate the
// underlying field.

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label?: string
    swatchClass?: string
    disabled?: boolean
  }>(),
  {
    label: '',
    swatchClass: 'h-9 w-12',
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { t } = useI18n()

const open = ref(false)
// HSV is the working representation while the modal is open — keeps the
// SV plane stable when the user drags purely on Value=0 / Saturation=0
// rows (which would collapse the RGB back-conversion otherwise).
const hueDeg = ref(0)
const sat = ref(0)
const val = ref(0)
const hexInput = ref('#000000')

function hexToRgb(hex: string): [number, number, number] | null {
  const trimmed = hex.trim()
  const m6 = /^#?([0-9a-fA-F]{6})$/.exec(trimmed)
  const m3 = /^#?([0-9a-fA-F]{3})$/.exec(trimmed)
  let body: string | null = null
  if (m6 && m6[1]) body = m6[1]
  else if (m3 && m3[1]) body = m3[1].split('').map((c) => c + c).join('')
  if (!body) return null
  return [
    parseInt(body.slice(0, 2), 16),
    parseInt(body.slice(2, 4), 16),
    parseInt(body.slice(4, 6), 16),
  ]
}

function rgbToHex(r: number, g: number, b: number): string {
  const toH = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0')
  return `#${toH(r)}${toH(g)}${toH(b)}`
}

function rgbToHsv(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const d = max - min
  let h = 0
  if (d !== 0) {
    if (max === rn) h = ((gn - bn) / d) % 6
    else if (max === gn) h = (bn - rn) / d + 2
    else h = (rn - gn) / d + 4
  }
  h = (h * 60 + 360) % 360
  return { h, s: max === 0 ? 0 : d / max, v: max }
}

function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const c = v * s
  const hp = h / 60
  const x = c * (1 - Math.abs((hp % 2) - 1))
  let r = 0
  let g = 0
  let b = 0
  if (hp < 1) {
    r = c
    g = x
  } else if (hp < 2) {
    r = x
    g = c
  } else if (hp < 3) {
    g = c
    b = x
  } else if (hp < 4) {
    g = x
    b = c
  } else if (hp < 5) {
    r = x
    b = c
  } else {
    r = c
    b = x
  }
  const m = v - c
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255]
}

function syncFromHex(hex: string): void {
  const rgb = hexToRgb(hex)
  if (!rgb) return
  const hsv = rgbToHsv(rgb[0], rgb[1], rgb[2])
  // Preserve current hue when entering pure greys — otherwise the SV
  // plane would jump back to red every time the user drags Value to 0.
  if (hsv.s > 0) hueDeg.value = hsv.h
  sat.value = hsv.s
  val.value = hsv.v
}

function openPicker(): void {
  if (props.disabled) return
  hexInput.value = props.modelValue || '#000000'
  syncFromHex(hexInput.value)
  open.value = true
}

const currentHex = computed(() => {
  const [r, g, b] = hsvToRgb(hueDeg.value, sat.value, val.value)
  return rgbToHex(r, g, b)
})

watch(currentHex, (next) => {
  // Keep the hex text input in sync with HSV drags, but only when the
  // modal is actually open — avoids spurious writes after confirm.
  if (open.value) hexInput.value = next
})

function applyHexInput(): void {
  const rgb = hexToRgb(hexInput.value)
  if (!rgb) {
    // Revert to the last valid value so a bad keystroke can't desync the
    // text field from the swatch.
    hexInput.value = currentHex.value
    return
  }
  syncFromHex(hexInput.value)
  hexInput.value = currentHex.value
}

const svRef = ref<HTMLDivElement | null>(null)
const hueRef = ref<HTMLDivElement | null>(null)

function onSVPointer(event: PointerEvent): void {
  const el = svRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left))
  const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top))
  sat.value = rect.width === 0 ? 0 : x / rect.width
  val.value = rect.height === 0 ? 0 : 1 - y / rect.height
}

function onSVDown(event: PointerEvent): void {
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  onSVPointer(event)
}

function onSVMove(event: PointerEvent): void {
  if (event.buttons === 1) onSVPointer(event)
}

function onHuePointer(event: PointerEvent): void {
  const el = hueRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left))
  hueDeg.value = rect.width === 0 ? 0 : (x / rect.width) * 360
}

function onHueDown(event: PointerEvent): void {
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  onHuePointer(event)
}

function onHueMove(event: PointerEvent): void {
  if (event.buttons === 1) onHuePointer(event)
}

const presets = [
  '#000000',
  '#ffffff',
  '#808080',
  '#c0c0c0',
  '#ff0000',
  '#ff7f00',
  '#ffff00',
  '#00ff00',
  '#00ffff',
  '#0000ff',
  '#7f00ff',
  '#ff00ff',
  '#8b4513',
  '#228b22',
  '#1e90ff',
  '#dc143c',
]

function pickPreset(hex: string): void {
  hexInput.value = hex
  syncFromHex(hex)
}

function confirm(): void {
  emit('update:modelValue', currentHex.value)
  open.value = false
}

function cancel(): void {
  open.value = false
}

function onKey(event: KeyboardEvent): void {
  if (!open.value) return
  if (event.key === 'Escape') cancel()
  else if (event.key === 'Enter' && (event.target as HTMLElement)?.tagName !== 'INPUT') confirm()
}

const hueColor = computed(() => {
  const [r, g, b] = hsvToRgb(hueDeg.value, 1, 1)
  return rgbToHex(r, g, b)
})
</script>

<template>
  <button
    type="button"
    class="shrink-0 cursor-pointer rounded border border-slate-700 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
    :class="swatchClass"
    :style="{ backgroundColor: modelValue }"
    :aria-label="label || t('colorPicker.title')"
    :title="modelValue"
    :disabled="disabled"
    @click="openPicker"
  />

  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      @click.self="cancel"
      @keydown="onKey"
    >
      <div class="w-full max-w-xs rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl">
        <h3 class="mb-3 text-sm font-semibold text-slate-100">
          {{ label || t('colorPicker.title') }}
        </h3>

        <div
          ref="svRef"
          class="relative h-40 w-full cursor-crosshair overflow-hidden rounded select-none touch-none"
          :style="{ backgroundColor: hueColor }"
          @pointerdown="onSVDown"
          @pointermove="onSVMove"
        >
          <div
            class="absolute inset-0"
            style="background: linear-gradient(to right, #fff, rgba(255,255,255,0))"
          />
          <div
            class="absolute inset-0"
            style="background: linear-gradient(to top, #000, rgba(0,0,0,0))"
          />
          <div
            class="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-lg"
            :style="{ left: `${sat * 100}%`, top: `${(1 - val) * 100}%` }"
          />
        </div>

        <div
          ref="hueRef"
          class="relative mt-3 h-4 w-full cursor-pointer rounded select-none touch-none"
          style="
            background: linear-gradient(
              to right,
              #f00 0%,
              #ff0 17%,
              #0f0 33%,
              #0ff 50%,
              #00f 67%,
              #f0f 83%,
              #f00 100%
            );
          "
          @pointerdown="onHueDown"
          @pointermove="onHueMove"
        >
          <div
            class="pointer-events-none absolute top-1/2 h-5 w-1 -translate-x-1/2 -translate-y-1/2 rounded border border-white shadow-lg"
            :style="{ left: `${(hueDeg / 360) * 100}%` }"
          />
        </div>

        <div class="mt-3 flex items-center gap-2">
          <span
            class="block h-10 w-10 shrink-0 rounded border border-slate-600"
            :style="{ backgroundColor: currentHex }"
            :aria-label="currentHex"
          />
          <input
            v-model="hexInput"
            type="text"
            class="flex-1 rounded border border-slate-700 bg-slate-800 px-2 py-1.5 font-mono text-xs text-slate-100"
            spellcheck="false"
            @change="applyHexInput"
            @keydown.enter.prevent="applyHexInput"
          />
        </div>

        <div class="mt-3 grid grid-cols-8 gap-1">
          <button
            v-for="p in presets"
            :key="p"
            type="button"
            class="aspect-square rounded border border-slate-600 hover:ring-2 hover:ring-slate-300"
            :style="{ backgroundColor: p }"
            :title="p"
            :aria-label="p"
            @click="pickPreset(p)"
          />
        </div>

        <div class="mt-4 flex justify-end gap-2">
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
            @click="cancel"
          >
            {{ t('colorPicker.cancel') }}
          </button>
          <button
            type="button"
            class="rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
            @click="confirm"
          >
            {{ t('colorPicker.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
