<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { nextPadColor, rec709Luminance, uniquePalette } from '../../../lib/paletteColors'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

// Palette card: pen-following vs manual mode plus the editable colour
// list (manual mode). The ``bitmap`` reactive object is passed by
// reference — child components in this file mutate it directly so the
// parent's deep watchers (which debounce /preview) pick up changes
// without a fan-out of v-model lines. This is a deliberate Vue idiom
// for tightly coupled internal forms; the bitmap shape is owned by
// SourceSection so the contract stays local to this folder.

import type { SegmentationMethod } from '../../../api/client'

interface BitmapDraft {
  segmentation_method: SegmentationMethod
  num_colors: number
  palette: string[]
  drop_background: boolean
  background_luminance: number
  // Other fields exist on the parent draft but aren't read here.
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapDraft
  paletteFollowsPens: boolean
  installedPenColors: string[]
  penSlotCount: number
  manualSwapCount: number
}>()

const emit = defineEmits<{
  (e: 'update:paletteFollowsPens', value: boolean): void
}>()

const { t } = useI18n()
const draft = useBitmapDraft()

// Three palette sources, derived from the existing draft state (no new
// field): follow installed pens, automatic k-means on ``num_colors``,
// or a hand-picked fixed palette. ``auto`` is the mode that frees the
// "number of colours" slider — without it the default pen-follow lock
// pins the cluster count to the installed-pen count and the slider
// reads as broken.
type PaletteSource = 'pens' | 'auto' | 'manual'
const source = computed<PaletteSource>(() => {
  // The segmentation METHOD is authoritative: kmeans / kmeans_lab render
  // the image's own colours ("auto"), whatever the legacy follows-pens
  // flag still says underneath. Without this the card showed "Suivre les
  // stylos" highlighted while the preview rendered the image's colours.
  if (
    props.bitmap.segmentation_method === 'kmeans' ||
    props.bitmap.segmentation_method === 'kmeans_lab'
  ) {
    return 'auto'
  }
  if (props.paletteFollowsPens) return 'pens'
  return props.bitmap.palette.length > 0 ? 'manual' : 'auto'
})

function selectPens(): void {
  // Pens-follow is a fixed_palette driven by the installed pens: set the
  // method here so the choice is explicit (the StyleTab watcher only
  // mirrors / truncates the pen palette, it no longer flips the method).
  emit('update:paletteFollowsPens', true)
  props.bitmap.segmentation_method = 'fixed_palette'
}

function selectAuto(): void {
  emit('update:paletteFollowsPens', false)
  // Automatic mode = k-means on ``num_colors``: clear any pinned palette
  // so the segmentation method is kmeans and the count slider drives the
  // result.
  props.bitmap.palette = []
  props.bitmap.segmentation_method = 'kmeans'
}

function selectManual(): void {
  emit('update:paletteFollowsPens', false)
  if (!props.bitmap.palette.length) {
    // Seed manual mode with the installed pens so the user has something
    // to edit instead of a blank list.
    props.bitmap.palette = [...props.installedPenColors]
  }
  props.bitmap.segmentation_method = 'fixed_palette'
}

function addPaletteColour(): void {
  // Distinct default per added chip: a repeated ``#888888`` merged into
  // one rendered layer (identical ``color-888888`` labels) so adding
  // colours never increased the visible count.
  props.bitmap.palette = [...props.bitmap.palette, nextPadColor(props.bitmap.palette)]
  // Pinning a colour implies fixed_palette — kmeans would ignore the
  // entry. Only rewrite when leaving the empty state (palette was
  // previously empty so no SvgTab choice could be in flight); once
  // we're already in fixed_palette, adding more chips doesn't need to
  // re-stomp the method. Avoids overwriting an explicit thresholds /
  // luminance_bands choice the operator made on the SVG tab between
  // colour additions.
  if (props.bitmap.palette.length === 1) {
    props.bitmap.segmentation_method = 'fixed_palette'
  }
}

function removePaletteColour(i: number): void {
  props.bitmap.palette = props.bitmap.palette.filter((_, idx) => idx !== i)
  // No more pinned colours → fall back to automatic kmeans on ``num_colors``.
  if (!props.bitmap.palette.length && props.bitmap.segmentation_method === 'fixed_palette') {
    props.bitmap.segmentation_method = 'kmeans'
  }
}

// Accept ``#rgb`` / ``#rrggbb`` (with or without the leading #), normalise
// to lowercase ``#rrggbb``. Returns null for anything else so a fat-fingered
// hex can't slip a non-colour string into the palette (which the colour
// swatch can't render and the backend would choke on).
function normalizeHex(raw: string): string | null {
  let s = raw.trim().toLowerCase()
  if (!s.startsWith('#')) s = `#${s}`
  if (/^#[0-9a-f]{3}$/.test(s)) {
    s = `#${s
      .slice(1)
      .split('')
      .map((c) => c + c)
      .join('')}`
  }
  return /^#[0-9a-f]{6}$/.test(s) ? s : null
}

function updatePaletteColour(i: number, value: string): void {
  const norm = normalizeHex(value)
  const next = [...props.bitmap.palette]
  // On invalid input keep the previous value; reassign the array regardless
  // so the text field's :value snaps back instead of retaining garbage.
  if (norm !== null) next[i] = norm
  props.bitmap.palette = next
}

// Palette entries the backend's drop-background filter will silently
// skip: with ``drop_background`` on, any layer whose colour sits at or
// above ``background_luminance`` is treated as paper and never drawn.
// Light pens (pale yellow, light grey…) used to just vanish with no
// explanation — surface them so the operator knows why a colour is
// missing from the preview.
const droppedAsBackground = computed<string[]>(() => {
  if (!props.bitmap.drop_background) return []
  if (
    props.bitmap.segmentation_method !== 'fixed_palette' &&
    props.bitmap.segmentation_method !== 'palette_dither'
  ) {
    return []
  }
  return uniquePalette(props.bitmap.palette).filter(
    (hex) => rec709Luminance(hex) >= props.bitmap.background_luminance,
  )
})
</script>

<template>
  <div class="card space-y-2 text-xs">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('palette.title') }}</p>
      <div class="flex overflow-hidden rounded border border-slate-700">
        <button
          type="button"
          class="px-2 py-0.5 text-[10px] transition disabled:cursor-not-allowed disabled:opacity-40"
          :class="
            source === 'pens' ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:bg-slate-800'
          "
          :disabled="!installedPenColors.length"
          :title="!installedPenColors.length ? t('palette.noPensInstalled') : undefined"
          @click="selectPens"
        >
          {{ t('palette.followPens') }}
        </button>
        <button
          type="button"
          class="border-l border-slate-700 px-2 py-0.5 text-[10px] transition"
          :class="
            source === 'auto' ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:bg-slate-800'
          "
          @click="selectAuto"
        >
          {{ t('palette.auto') }}
        </button>
        <button
          type="button"
          class="border-l border-slate-700 px-2 py-0.5 text-[10px] transition"
          :class="
            source === 'manual'
              ? 'bg-slate-700 text-slate-100'
              : 'text-slate-400 hover:bg-slate-800'
          "
          @click="selectManual"
        >
          {{ t('palette.manual') }}
        </button>
      </div>
    </div>

    <!-- Number of colours lives on a single slider in
         ``ColorCountSlider`` (just above the style picker)
         so the operator has one knob, not two. In pens mode the
         StyleTab watcher truncates the palette to ``num_colors``; in
         auto mode num_colors drives k-means; in manual mode the slider
         resizes the editable palette below. -->

    <!-- Pen-following: chips locked to the installed pens, with slot
         numbers so the user knows which pen will plot what. -->
    <div v-if="source === 'pens'" class="space-y-1.5">
      <p v-if="!installedPenColors.length" class="text-[10px] text-amber-300">
        {{ t('palette.noPensInstalled') }}
      </p>
      <div v-else class="flex flex-wrap gap-1.5">
        <span
          v-for="(color, i) in installedPenColors"
          :key="i"
          class="inline-flex items-center gap-1 rounded border border-slate-600 bg-slate-900 px-1.5 py-0.5"
          :title="t('palette.slotTooltip', { index: i, color })"
        >
          <span
            class="inline-block h-3 w-3 rounded border border-slate-600"
            :style="{ backgroundColor: color }"
          />
          <span class="font-mono text-[10px] text-slate-400">#{{ i }}</span>
          <span class="font-mono text-[10px] text-slate-200">{{ color }}</span>
        </span>
      </div>
      <p class="text-[10px] text-slate-500">{{ t('palette.followHint') }}</p>
    </div>

    <!-- Auto: k-means on the chosen number of colours (input above). -->
    <div v-else-if="source === 'auto'" class="space-y-2">
      <p class="text-[10px] text-slate-500">{{ t('palette.autoHint') }}</p>
    </div>

    <!-- Manual: editable palette + add. -->
    <div v-else class="space-y-2">
      <div class="space-y-1">
        <div class="flex items-center justify-between">
          <span class="inline-flex items-center text-slate-400">
            {{ t('convert.specificColors') }}
            <LayerCountBadge
              v-if="bitmap.segmentation_method === 'fixed_palette' && bitmap.palette.length > 0"
              :count="draft.expectedLayerCount.value"
            />
          </span>
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-slate-600"
            @click="addPaletteColour"
          >
            + {{ t('convert.addColour') }}
          </button>
        </div>
        <p v-if="!bitmap.palette.length" class="text-[10px] text-slate-500">
          {{ t('convert.specificColorsHint') }}
        </p>
        <div v-for="(hex, i) in bitmap.palette" :key="i" class="flex items-center gap-1">
          <input
            type="color"
            :value="hex"
            class="h-7 w-12 cursor-pointer rounded border border-slate-700 bg-slate-900"
            @input="(e) => updatePaletteColour(i, (e.target as HTMLInputElement).value)"
          />
          <input
            type="text"
            :value="hex"
            maxlength="7"
            placeholder="#rrggbb"
            :aria-label="t('convert.specificColors')"
            class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
            @change="(e) => updatePaletteColour(i, (e.target as HTMLInputElement).value)"
          />
          <button
            type="button"
            class="rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
            @click="removePaletteColour(i)"
          >
            ✕
          </button>
        </div>
      </div>
    </div>

    <p
      v-if="droppedAsBackground.length > 0"
      class="flex flex-wrap items-center gap-1 rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-[11px] text-amber-200"
    >
      ⚠ {{ t('palette.droppedAsBackground') }}
      <span
        v-for="hex in droppedAsBackground"
        :key="hex"
        class="inline-flex items-center gap-1 rounded border border-amber-800 bg-slate-900 px-1 py-0.5"
      >
        <span
          class="inline-block h-2.5 w-2.5 rounded border border-slate-600"
          :style="{ backgroundColor: hex }"
        />
        <span class="font-mono text-[10px]">{{ hex }}</span>
      </span>
    </p>

    <p
      v-if="manualSwapCount > 0"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-[11px] text-amber-200"
    >
      ⚠
      {{
        t('palette.manualSwap', {
          count: manualSwapCount,
          total: bitmap.palette.length,
          slots: penSlotCount,
        })
      }}
    </p>
  </div>
</template>
