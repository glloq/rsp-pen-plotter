<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { nextPadColor, uniquePalette } from '../../../lib/paletteColors'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import LayerCountBadge from '../shared/LayerCountBadge.vue'

// Cluster-count slider, extracted from ``MultiColorMasterStyleParams``
// so the Style tab can show it BEFORE the master-style picker: the
// operator first decides how many colours the print uses, then which
// style draws them. This is the **single** num_colors knob in the
// editor — the PaletteCard intentionally doesn't expose its own input
// so the operator has one place, not two, to change colour count.
//
// What the slider does, by palette source:
//   * pens     — StyleTab watcher truncates ``bitmap.palette`` to
//                ``num_colors`` so the preview uses only the first N
//                installed pens.
//   * auto     — ``num_colors`` drives the k-means cluster count.
//   * manual   — fixed_palette ignores ``num_colors`` downstream
//                (the palette length wins), so the setter resizes
//                the palette in lock-step: truncate when smaller,
//                pad with neutral grey when bigger.

interface BitmapLike {
  num_colors: number
  palette: string[]
  segmentation_method: string
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
}>()

const { t } = useI18n()
const draft = useBitmapDraft()
// Non-owner handle on the shared previewer so the slider can compare
// "requested" with what the live /preview ACTUALLY rendered.
const fm = useFileManager(t)

const numColors = computed({
  get: () => props.bitmap.num_colors,
  set: (v: number) => {
    const target = Math.max(1, Math.min(16, Math.round(v)))
    props.bitmap.num_colors = target
    draft.markSegmentationTouched('num_bands') // close enough family

    // Manual-palette resize: only when the operator is hand-editing a
    // fixed palette (not following pens — that path is handled by the
    // StyleTab watcher, which knows the installed-pen list to slice).
    if (
      props.bitmap.segmentation_method === 'fixed_palette' &&
      props.bitmap.palette.length > 0 &&
      !draft.paletteFollowsPens.value
    ) {
      const current = props.bitmap.palette
      if (current.length > target) {
        props.bitmap.palette = current.slice(0, target)
      } else if (current.length < target) {
        // Pad with *distinct* defaults: repeated ``#888888`` chips used
        // to merge into a single rendered layer (identical labels) while
        // the grey stole every mid-tone pixel — asking for 6 colours
        // displayed fewer than 4.
        const padded = [...current]
        while (padded.length < target) padded.push(nextPadColor(padded))
        props.bitmap.palette = padded
      }
    }
  },
})

// What the segmentation will actually produce, as opposed to what the
// slider asks for: palette-driven methods walk the (deduped) palette,
// so a pens-following palette capped at the installed-pen count wins
// over a higher ``num_colors``.
const effectiveColorCount = computed(() => {
  const b = props.bitmap
  if (
    (b.segmentation_method === 'fixed_palette' || b.segmentation_method === 'palette_dither') &&
    b.palette.length > 0
  ) {
    return uniquePalette(b.palette).length
  }
  return b.num_colors
})

// What the live /preview actually rendered. The backend legitimately
// produces FEWER clusters than requested — k is capped at the image's
// distinct colours, near-identical hues merge (ΔE threshold), and
// light clusters are dropped as background — but without surfacing
// that here the operator reads "I selected 6, it shows 4" as a bug.
// ``null`` until a preview lands; the previewer singleton is cleared
// on placement switch so a stale count can't leak across files.
const renderedCount = computed<number | null>(() => {
  const palette = fm.previewResult?.value?.palette
  return palette && palette.length > 0 ? palette.length : null
})
const renderedDiffers = computed<boolean>(
  () => renderedCount.value !== null && renderedCount.value !== effectiveColorCount.value,
)

// Pens-following palettes silently cap at the installed-pen count; the
// slider used to keep displaying the requested value with no hint of
// why nothing changed past N. Surface the cap explicitly.
const pensCapShortfall = computed(() => {
  if (!draft.paletteFollowsPens.value) return 0
  const b = props.bitmap
  if (b.segmentation_method !== 'fixed_palette' && b.segmentation_method !== 'palette_dither')
    return 0
  if (!b.palette.length) return 0
  return Math.max(0, b.num_colors - uniquePalette(b.palette).length)
})
</script>

<template>
  <div class="space-y-1">
    <div class="flex items-center justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ t('colorStyles.numColors') }}
        <LayerCountBadge :count="draft.expectedLayerCount.value" />
      </p>
      <span class="font-mono text-[11px] text-slate-300">{{ effectiveColorCount }}</span>
    </div>
    <input
      :value="numColors"
      type="range"
      :min="2"
      :max="16"
      step="1"
      class="w-full accent-emerald-500"
      @input="(e) => (numColors = Number((e.target as HTMLInputElement).value))"
    />
    <p class="text-[10px] text-slate-500">
      {{ t('colorStyles.numColorsHint') }}
    </p>
    <p
      v-if="renderedDiffers"
      class="rounded border border-slate-700 bg-slate-900/60 px-2 py-1 text-[10px] leading-snug text-slate-300"
      data-test="num-colors-rendered"
    >
      {{
        t('colorStyles.numColorsRendered', {
          requested: effectiveColorCount,
          rendered: renderedCount,
        })
      }}
    </p>
    <p
      v-if="pensCapShortfall > 0"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-[10px] leading-snug text-amber-200"
    >
      {{
        t('colorStyles.numColorsCapped', {
          requested: bitmap.num_colors,
          available: effectiveColorCount,
        })
      }}
    </p>
  </div>
</template>
