<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useToastStore } from '../stores/toasts'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const store = useJobStore()
const toasts = useToastStore()
const ui = useUiStore()

// Sheet orientation. Defaults to match the machine work area shape (a wide
// bed → landscape, a tall bed → portrait) once the profile is known, but
// the operator can override it; presets then apply in the chosen
// orientation. ``orientationInit`` guards the one-shot default so a later
// profile reload doesn't clobber a manual choice.
type Orientation = 'portrait' | 'landscape'
const orientation = ref<Orientation>('portrait')
let orientationInit = false

// Drafts mirror the saved sheet so the user can tweak without overwriting on
// each keystroke. We commit on Apply / preset click / explicit centre.
const widthDraft = ref(0)
const heightDraft = ref(0)
const offsetXDraft = ref(0)
const offsetYDraft = ref(0)

watch(
  () => store.currentDrawing,
  (drawing) => {
    if (!drawing) return
    widthDraft.value = Number(drawing.width_mm.toFixed(2))
    heightDraft.value = Number(drawing.height_mm.toFixed(2))
    offsetXDraft.value = Number(drawing.x_mm.toFixed(2))
    offsetYDraft.value = Number(drawing.y_mm.toFixed(2))
  },
  { immediate: true, deep: true },
)

const workspaceWidth = computed(() => {
  const ws = store.selectedProfile?.workspace
  return ws ? ws.x_max - ws.x_min : 0
})
const workspaceHeight = computed(() => {
  const ws = store.selectedProfile?.workspace
  return ws ? ws.y_max - ws.y_min : 0
})

// Seed the default orientation from the work area shape, once, as soon as
// the profile dimensions are available.
watch(
  [workspaceWidth, workspaceHeight],
  ([w, h]) => {
    if (orientationInit || w <= 0 || h <= 0) return
    orientation.value = w > h ? 'landscape' : 'portrait'
    orientationInit = true
  },
  { immediate: true },
)

function setOrientation(o: Orientation): void {
  orientation.value = o
  orientationInit = true
  // Re-shape the current sheet so its long side matches the orientation.
  const big = Math.max(widthDraft.value, heightDraft.value)
  const small = Math.min(widthDraft.value, heightDraft.value)
  widthDraft.value = o === 'landscape' ? big : small
  heightDraft.value = o === 'landscape' ? small : big
  applySheet()
}

const sheetExceedsWorkspace = computed(
  () =>
    widthDraft.value > workspaceWidth.value + 0.01 ||
    heightDraft.value > workspaceHeight.value + 0.01 ||
    offsetXDraft.value + widthDraft.value > workspaceWidth.value + 0.01 ||
    offsetYDraft.value + heightDraft.value > workspaceHeight.value + 0.01,
)

interface SheetPreset {
  name: string
  w: number
  h: number
}
const presets: SheetPreset[] = [
  { name: 'A6', w: 105, h: 148 },
  { name: 'A5', w: 148, h: 210 },
  { name: 'A4', w: 210, h: 297 },
  { name: 'A3', w: 297, h: 420 },
  { name: 'A2', w: 420, h: 594 },
  { name: 'Letter', w: 216, h: 279 },
]

function applyPreset(p: SheetPreset): void {
  // Presets are defined portrait (w < h); swap for landscape so the chosen
  // orientation is honoured.
  const landscape = orientation.value === 'landscape'
  const width = landscape ? p.h : p.w
  const height = landscape ? p.w : p.h
  widthDraft.value = width
  heightDraft.value = height
  // Display the chosen sheet on the workspace plan (top-left, transparent).
  ui.setPreviewSheet({ width_mm: width, height_mm: height })
  // Centre on apply so the sheet ends up nicely positioned by default.
  centreSheet(width, height)
}

function centreSheet(width = widthDraft.value, height = heightDraft.value): void {
  offsetXDraft.value = Math.max(0, (workspaceWidth.value - width) / 2)
  offsetYDraft.value = Math.max(0, (workspaceHeight.value - height) / 2)
  applySheet()
}

function applySheet(): void {
  const w = Number(widthDraft.value)
  const h = Number(heightDraft.value)
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    toasts.error(t('sheet.invalidSize'))
    return
  }
  store.setDrawing({
    width_mm: w,
    height_mm: h,
    x_mm: Math.max(0, Number(offsetXDraft.value) || 0),
    y_mm: Math.max(0, Number(offsetYDraft.value) || 0),
  })
}

function resetToFullWorkspace(): void {
  store.resetDrawing()
}
</script>

<template>
  <section v-if="store.layers.length || store.selectedProfile" class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.layout') }}</h2>
    </div>

    <div
      v-if="store.selectedProfile"
      class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3"
    >
      <p class="text-[10px] text-slate-500">
        {{ t('sheet.workArea') }}:
        <span class="font-mono text-slate-300">
          {{ workspaceWidth.toFixed(0) }}×{{ workspaceHeight.toFixed(0) }} mm
        </span>
        <span class="text-slate-600"> · {{ t('sheet.workAreaHint') }}</span>
      </p>

      <div>
        <span class="mb-1 block text-[10px] uppercase tracking-wider text-slate-500">
          {{ t('sheet.orientation') }}
        </span>
        <div class="grid grid-cols-2 gap-1">
          <button
            type="button"
            class="rounded border px-2 py-1 text-[11px] transition"
            :class="
              orientation === 'portrait'
                ? 'border-emerald-500 bg-emerald-950/40 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
            "
            :aria-pressed="orientation === 'portrait'"
            @click="setOrientation('portrait')"
          >
            ▯ {{ t('sheet.portrait') }}
          </button>
          <button
            type="button"
            class="rounded border px-2 py-1 text-[11px] transition"
            :class="
              orientation === 'landscape'
                ? 'border-emerald-500 bg-emerald-950/40 text-emerald-200'
                : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'
            "
            :aria-pressed="orientation === 'landscape'"
            @click="setOrientation('landscape')"
          >
            ▭ {{ t('sheet.landscape') }}
          </button>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-1">
        <button
          v-for="p in presets"
          :key="p.name"
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300 hover:border-slate-600"
          @click="applyPreset(p)"
        >
          {{ p.name }}
          <span class="block text-[9px] text-slate-500">
            {{ orientation === 'landscape' ? p.h : p.w }}×{{
              orientation === 'landscape' ? p.w : p.h
            }}
          </span>
        </button>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <label class="block text-xs text-slate-400">
          {{ t('sheet.width') }}
          <input
            v-model.number="widthDraft"
            type="number"
            min="1"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
        <label class="block text-xs text-slate-400">
          {{ t('sheet.height') }}
          <input
            v-model.number="heightDraft"
            type="number"
            min="1"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <label class="block text-xs text-slate-400">
          {{ t('sheet.offsetX') }}
          <input
            v-model.number="offsetXDraft"
            type="number"
            min="0"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
        <label class="block text-xs text-slate-400">
          {{ t('sheet.offsetY') }}
          <input
            v-model.number="offsetYDraft"
            type="number"
            min="0"
            step="any"
            class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
          />
        </label>
      </div>

      <div class="flex gap-1">
        <button
          type="button"
          class="flex-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
          @click="applySheet"
        >
          {{ t('sheet.applySize') }}
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-600"
          @click="centreSheet()"
        >
          {{ t('sheet.centre') }}
        </button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-600"
          @click="resetToFullWorkspace"
        >
          {{ t('sheet.useFullWorkspace') }}
        </button>
      </div>

      <p v-if="sheetExceedsWorkspace" class="text-[10px] text-amber-300">
        ⚠ {{ t('sheet.exceedsWarning') }}
      </p>
    </div>

    <div
      v-if="store.layers.length"
      class="grid grid-cols-2 gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm"
    >
      <label class="block text-slate-400">
        {{ t('job.scaleMode') }}
        <select
          v-model="store.scaleMode"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        >
          <option value="fit">{{ t('job.scaleFit') }}</option>
          <option value="actual">{{ t('job.scaleActual') }}</option>
        </select>
      </label>
      <label class="block text-slate-400" :class="{ 'opacity-40': store.scaleMode !== 'fit' }">
        {{ t('job.margin') }}
        <input
          v-model.number="store.marginMm"
          type="number"
          step="any"
          min="0"
          :disabled="store.scaleMode !== 'fit'"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
    </div>
  </section>
</template>
