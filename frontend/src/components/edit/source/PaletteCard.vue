<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
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
  if (props.paletteFollowsPens) return 'pens'
  return props.bitmap.palette.length > 0 ? 'manual' : 'auto'
})

function selectPens(): void {
  // The StyleTab watcher rewrites segmentation → fixed_palette + the
  // installed-pen colours when paletteFollowsPens flips back on.
  emit('update:paletteFollowsPens', true)
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
  props.bitmap.palette = [...props.bitmap.palette, '#888888']
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

function updatePaletteColour(i: number, value: string): void {
  const next = [...props.bitmap.palette]
  next[i] = value
  props.bitmap.palette = next
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2 text-xs">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">{{ t('palette.title') }}</p>
      <div class="flex overflow-hidden rounded border border-slate-700">
        <button
          type="button"
          class="px-2 py-0.5 text-[10px] transition"
          :class="
            source === 'pens' ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:bg-slate-800'
          "
          :disabled="!installedPenColors.length"
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

    <!-- Auto: k-means on a freely-chosen number of colours. -->
    <div v-else-if="source === 'auto'" class="space-y-2">
      <label class="block text-slate-400">
        {{ t('convert.numColors') }}
        <LayerCountBadge :count="draft.expectedLayerCount.value" />
        <input
          v-model.number="bitmap.num_colors"
          type="number"
          min="1"
          max="16"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
      </label>
      <p class="text-[10px] text-slate-500">{{ t('palette.autoHint') }}</p>
    </div>

    <!-- Manual: editable palette + add. -->
    <div v-else class="space-y-2">
      <label class="block text-slate-400">
        {{ t('convert.numColors') }}
        <input
          v-model.number="bitmap.num_colors"
          type="number"
          min="1"
          max="16"
          :disabled="bitmap.segmentation_method === 'fixed_palette' && bitmap.palette.length > 0"
          class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
        />
      </label>

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
