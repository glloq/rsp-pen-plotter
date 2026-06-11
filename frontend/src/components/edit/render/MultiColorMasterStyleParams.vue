<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMulticolorStyle } from '../../../data/printRegistry'
import { nextPadColor, uniquePalette } from '../../../lib/paletteColors'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { useJobStore } from '../../../stores/job'
import LayerCountBadge from '../shared/LayerCountBadge.vue'
import MasterStyleKnobs from './MasterStyleKnobs.vue'

// Per-style operator knobs for the multicolour master family — sibling
// of ``MasterStyleParams.vue`` but for the colour-recipe pipeline. The
// per-style knob UI is declarative (``data/styleKnobs.ts`` descriptors
// rendered by the shared ``MasterStyleKnobs`` component), so a new
// colour master needs zero edits here. This card keeps only the
// colour-specific chrome: the cluster-count slider and the style
// description line. ``num_colors`` lives here (not on the PaletteCard)
// so the operator has one place, not two, to change colour count.

interface BitmapLike {
  num_colors: number
  palette: string[]
  segmentation_method: string
  [key: string]: unknown
}

const props = defineProps<{
  bitmap: BitmapLike
  styleId: string
}>()

const { t } = useI18n()
const draft = useBitmapDraft()
const store = useJobStore()

const style = computed(() => resolveMulticolorStyle(props.styleId))

const knobs = computed(() => draft.getMulticolorStyleKnobs(props.styleId))

// Trailing-edge throttle — twin of MasterStyleParams. A slider drag
// fires one @input per pixel; the knob write below is immediate (live
// preview feedback) but the per-layer store propagation only needs to
// run once, shortly after the drag settles.
const KNOB_PROPAGATION_DELAY_MS = 120
let knobPropagationTimer: ReturnType<typeof setTimeout> | null = null

function setKnob<K extends string>(key: K, value: unknown): void {
  ;(draft.setMulticolorKnob as any)(props.styleId, key, value)
  // Push the updated knobs onto existing layers so /rerender (gcode
  // generation) reflects the slider change. /preview ships
  // ``band_recipes`` computed fresh from knobs and works without this,
  // but the persisted ``layer_algorithms`` would otherwise stay on the
  // values captured at upload time — the editor preview and the gcode
  // output would diverge as soon as the operator tweaks any knob
  // (crossed, angle_step, spacing range, …).
  if (store.layers.length > 0) {
    if (knobPropagationTimer !== null) clearTimeout(knobPropagationTimer)
    knobPropagationTimer = setTimeout(() => {
      knobPropagationTimer = null
      void applyMasterStyleToLayers(store, {
        styleId: props.styleId,
        penSlot: null,
        recipeResolver: (index, total, hex) => draft.multicolorRecipeForCluster(index, total, hex),
      })
    }, KNOB_PROPAGATION_DELAY_MS)
  }
}

// Cluster count surfaced at the top so the operator gets the same
// orientation cue as the mono card's "bands" slider. This is the
// **single** num_colors knob in the editor — the PaletteCard
// intentionally doesn't expose its own input so the operator has one
// place, not two, to change colour count.
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
  <div class="space-y-3">
    <!-- Cluster count slider (twin of mono's "Shades") -->
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

    <!-- ===== Per-style knob block — declarative (data/styleKnobs.ts) ===== -->
    <MasterStyleKnobs family="multicolor" :style-id="styleId" :knobs="knobs" @set="setKnob" />

    <p class="text-[10px] text-slate-500">
      {{ style.descriptionKey ? t(style.descriptionKey) : '' }}
    </p>
  </div>
</template>
