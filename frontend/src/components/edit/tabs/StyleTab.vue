<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { resolveEffectivePalette } from '../../../lib/effectivePalette'
import { uniquePalette } from '../../../lib/paletteColors'
import { canonicalHex, strokeWidthMmByHex } from '../../../lib/penWidth'
import { useAvailableColorsStore } from '../../../stores/availableColors'
import { useJobStore } from '../../../stores/job'
import { usePaletteSourceStore } from '../../../stores/paletteSource'
import ColorModeCard from '../colors/ColorModeCard.vue'
import ColorCountSlider from '../render/ColorCountSlider.vue'
import MasterStylePicker from '../render/MasterStylePicker.vue'
import MasterStyleParams from '../render/MasterStyleParams.vue'
import MultiColorMasterStyleParams from '../render/MultiColorMasterStyleParams.vue'
import PaletteCard from '../source/PaletteCard.vue'
import PenSlotPicker from '../shared/PenSlotPicker.vue'
import PostProcessCard from '../style/PostProcessCard.vue'
import TabEmptyState from '../shared/TabEmptyState.vue'

// Style tab — focused on *what* the rendered bitmap output looks like:
//   - bitmap mono  → master style picker, per-style params, pen slot,
//                    plus post-process filters
//   - bitmap multi → color-mode toggle, palette (manual / follows pens),
//                    plus post-process filters
//
// Text-specific controls (font, Hershey toggle, block map for mixed
// text + image documents) moved to the dedicated Text tab so the Style
// surface stays focused on rendering knobs. The image → SVG technical
// knobs (detail tier, centerline mode, simplification, segmentation
// method) live on the sibling SVG tab.

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const store = useJobStore()

const bitmap = draft.bitmap
const printMode = draft.printMode

const installedPenColors = computed<string[]>(() => {
  const pens = store.selectedProfile?.pens ?? []
  return pens.filter((p) => p.installed && p.color).map((p) => p.color)
})

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

// Effective palette = the pool the per-layer picker reads from, driven
// by the operator's palette-source toggle in the Plotter drawer. The
// legacy ``paletteFollowsPens`` boolean still exists in the bitmap
// draft for back-compat with persisted placements (rehydrate reads it
// from ``last_options``); the new ``palette_source`` setting takes
// precedence at render time.
const paletteSource = usePaletteSourceStore()
const availableColorsStore = useAvailableColorsStore()

onMounted(() => {
  if (!paletteSource.loaded) void paletteSource.refresh()
  if (!availableColorsStore.loaded) void availableColorsStore.refresh()
})

const availableHexes = computed<string[]>(() => availableColorsStore.ordered.map((c) => c.hex))

const effectivePalette = computed<string[]>(() =>
  resolveEffectivePalette(paletteSource.source, installedPenColors.value, availableHexes.value),
)

// Pen tip diameters (mm) keyed by colour, from the owned-ink inventory.
// These floor the per-style "dot radius" / "stroke width" knobs at the
// physical mark the chosen pen makes — you can't draw thinner than the
// tip. ``null`` when the colour carries no declared width.
const strokeWidthByHex = computed(() => strokeWidthMmByHex(availableColorsStore.colors))

const monoPenWidthMm = computed<number | null>(
  () => strokeWidthByHex.value.get(canonicalHex(draft.mono.value.ink_color)) ?? null,
)

// Multicolour: floor at the THINNEST pen in the effective palette — the
// global knob applies to every colour, and the thinnest mark achievable
// across them is set by the finest tip. Thicker pens simply draw their
// own (wider) tip regardless of the knob.
const multicolorPenWidthMm = computed<number | null>(() => {
  let min: number | null = null
  for (const hex of effectivePalette.value) {
    const w = strokeWidthByHex.value.get(canonicalHex(hex))
    if (w !== undefined && (min === null || w < min)) min = w
  }
  return min
})

// When the operator turned ``palette-follows-pens`` on AND the
// effective palette has at least one chip, mirror it into the draft
// palette + seed the segmentation method as ``fixed_palette``. The
// palette is truncated to ``bitmap.num_colors`` so the operator can
// use fewer pens than installed (e.g. only the first 4 of 6 magazine
// slots) — without that, the "Nombre de couleurs" inputs would write
// to ``num_colors`` but the preview would keep rendering with all 6
// pens because ``fixed_palette`` walks the entire palette array.
// Guarded against stomping a mono-mode rehydrate (only seed genuine
// multicolour placements).
watch(
  [draft.paletteFollowsPens, effectivePalette, () => bitmap.value.num_colors],
  ([follows, colors, n]) => {
    if (printMode.value !== 'multicolor') return
    if (follows && colors.length) {
      // Dedupe before slicing: two installed pens with the same ink
      // would otherwise eat two of the operator's N colour slots while
      // rendering as a single layer (the backend merges identical
      // palette entries).
      const distinct = uniquePalette(colors)
      // The FULL rack feeds the backend's ink_pool (which inks each
      // cluster can snap to). Without this the truncated palette below
      // capped the pool at the first N slots, so blue drew as red /
      // green as yellow when the matching pens sat further down the rack.
      draft.pensFullPool.value = distinct
      // The truncated palette only drives the colour-count displays
      // (num_colors), not which inks are reachable.
      const limit = Math.min(distinct.length, Math.max(1, Number(n) || distinct.length))
      bitmap.value.palette = distinct.slice(0, limit)
      // Only seed ``fixed_palette`` as the default pens-mode method when
      // the operator hasn't explicitly chosen a segmentation method in
      // the SVG tab. Picking kmeans / kmeans_lab there marks ``method``
      // touched; honouring it keeps the perceptual clustering the
      // operator selected (which renders the image's own colours)
      // instead of silently snapping every cluster onto the pen rack —
      // the "couleurs pas adaptées" the operator saw when this watch
      // fired ``immediate`` on tab entry and clobbered their choice.
      if (!draft.segmentationTouched.value.has('method')) {
        bitmap.value.segmentation_method = 'fixed_palette'
      }
    }
  },
  { immediate: true },
)

const manualSwapCount = computed(() =>
  Math.max(0, bitmap.value.palette.length - penSlotCount.value),
)

function setPaletteFollowsPens(value: boolean): void {
  draft.paletteFollowsPens.value = value
}

// Switching master style: rewrite the draft's segmentation + uniform
// algorithm via the centralised helper. Changing the config in the
// editor is a routine, fully-reversible action, so it no longer
// interrupts the operator with a warning toast or an override-replace
// confirmation — the only confirmation left is when *saving* (Apply)
// over an existing conversion. ``force: true`` therefore applies the
// preset unconditionally. When layers already exist (post-upload), the
// per-band recipe is re-propagated across them so the live preview
// reflects the new style without needing a re-upload.
async function onMasterStyleChange(id: string): Promise<void> {
  const previous = draft.monoMasterStyleId.value
  draft.setMasterStyle(id, { force: true })

  if (store.layers.length > 0 && previous !== id) {
    await applyMasterStyleToLayers(store, {
      styleId: id,
      penSlot: draft.monoPenSlot.value,
      // Honour the operator's live mono sliders so the per-layer
      // recipes match the preview instead of the registry defaults.
      recipeResolver: (index, total) => draft.monoRecipeForBand(index, total),
    })
  }
}

// Multicolour twin of ``onMasterStyleChange`` — same silent preset
// application + post-upload propagation, just driving the multicolour
// master.
async function onMulticolorMasterStyleChange(id: string): Promise<void> {
  const previous = draft.multicolorMasterStyleId.value
  draft.setMulticolorMasterStyle(id, { force: true })

  if (store.layers.length > 0 && previous !== id) {
    // Multicolour styles don't have a target pen slot — each layer
    // already carries its own ``target_pen_slot`` from segmentation /
    // pen matching, so just push the default algorithm + options.
    // The resolver feeds the operator's live multicolour sliders
    // (spacing / density / angle-step ranges) so the per-cluster
    // recipes match the preview.
    await applyMasterStyleToLayers(store, {
      styleId: id,
      penSlot: null,
      recipeResolver: (index, total, hex) => draft.multicolorRecipeForCluster(index, total, hex),
    })
  }
}
</script>

<template>
  <!-- Bitmap or document (PDF). Document sources still expose every
       bitmap rendering knob because the PDF/DOCX raster regions go
       through the same segmentation pipeline; the text-specific cards
       (Hershey toggle, font, block map) moved to the dedicated Text
       tab so this surface stays focused on bitmap rendering. -->
  <section v-if="fm.showsBitmapForm.value" class="space-y-3">
    <ColorModeCard :mode="printMode" @update:mode="(mode) => draft.setPrintMode(mode)" />

    <template v-if="printMode === 'monochrome'">
      <div class="card space-y-3 text-xs">
        <PenSlotPicker
          :model-value="draft.monoPenSlot.value"
          @update:model-value="(v) => (draft.monoPenSlot.value = v)"
        />

        <MasterStylePicker
          :model-value="draft.monoMasterStyleId.value"
          @update:model-value="onMasterStyleChange"
        />

        <MasterStyleParams
          :bitmap="bitmap"
          :style-id="draft.monoMasterStyleId.value"
          :min-pen-width-mm="monoPenWidthMm"
        />

        <p
          class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400"
        >
          {{ t('mono.layersHint') }}
        </p>
      </div>
    </template>

    <template v-else>
      <div class="card space-y-3 text-xs">
        <!-- Colour count first, then the style that draws those
             colours — the count constrains which styles make sense,
             so the operator decides it before picking a style. -->
        <ColorCountSlider :bitmap="bitmap" />

        <MasterStylePicker
          mode="multicolor"
          :model-value="draft.multicolorMasterStyleId.value"
          @update:model-value="onMulticolorMasterStyleChange"
        />

        <MultiColorMasterStyleParams
          :style-id="draft.multicolorMasterStyleId.value"
          :min-pen-width-mm="multicolorPenWidthMm"
        />
      </div>

      <PaletteCard
        :bitmap="bitmap"
        :palette-follows-pens="draft.paletteFollowsPens.value"
        :installed-pen-colors="effectivePalette"
        :pen-slot-count="penSlotCount"
        :manual-swap-count="manualSwapCount"
        @update:palette-follows-pens="setPaletteFollowsPens"
      />
      <p
        class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400"
      >
        {{ t('render.multicolorHint') }}
      </p>
    </template>

    <PostProcessCard :bitmap="bitmap" />
  </section>

  <TabEmptyState v-else :message="t('style.notApplicable')" />
</template>
