<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getFonts } from '../../../api/client'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { resolveEffectivePalette } from '../../../lib/effectivePalette'
import { useAvailableColorsStore } from '../../../stores/availableColors'
import { useJobStore } from '../../../stores/job'
import { usePaletteSourceStore } from '../../../stores/paletteSource'
import BlockMapCard from '../BlockMapCard.vue'
import ColorModeCard from '../colors/ColorModeCard.vue'
import MasterStylePicker from '../render/MasterStylePicker.vue'
import MasterStyleParams from '../render/MasterStyleParams.vue'
import MultiColorMasterStyleParams from '../render/MultiColorMasterStyleParams.vue'
import PaletteCard from '../source/PaletteCard.vue'
import PenSlotPicker from '../shared/PenSlotPicker.vue'
import PostProcessCard from '../style/PostProcessCard.vue'
import TypographyCard from '../source/TypographyCard.vue'

// Style tab — merges the former "Colors" and "Render" tabs into one
// surface focused on *what* the rendered output looks like:
//   - bitmap mono  → master style picker, per-style params, pen slot,
//                    plus post-process filters
//   - bitmap multi → color-mode toggle, palette (manual / follows pens),
//                    plus post-process filters
//   - typography   → TypographyCard (font, size, line spacing, page)
//   - document/PDF → BlockMapCard on top of the bitmap controls (PDF
//                    pages get rasterised so the bitmap controls still
//                    apply to the raster portion)
//
// The image → SVG technical knobs (detail tier, centerline mode,
// simplification, segmentation method) live on the sibling SVG tab.

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

// When the operator turned ``palette-follows-pens`` on AND the
// effective palette has at least one chip, mirror it into the draft
// palette + lock the segmentation method to ``fixed_palette``.
// Guarded against stomping a mono-mode rehydrate (only seed genuine
// multicolour placements).
watch(
  [draft.paletteFollowsPens, effectivePalette],
  ([follows, colors]) => {
    if (printMode.value !== 'multicolor') return
    if (follows && colors.length) {
      bitmap.value.palette = [...colors]
      bitmap.value.segmentation_method = 'fixed_palette'
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

// Font catalogue for TypographyCard (.txt / .md sources). Local to
// this tab rather than the singleton because no other tab needs it.
const fonts = ref<string[]>([])
onMounted(async () => {
  try {
    fonts.value = await getFonts()
  } catch {
    /* keep [] */
  }
})

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
  <!-- Typography source: dedicated card replaces the bitmap content. -->
  <section v-if="fm.kind.value === 'typography'" class="space-y-3">
    <TypographyCard :typo="draft.typo.value" :fonts="fonts" mode="typography" />
  </section>

  <!-- Bitmap or document (PDF). Document gets a BlockMapCard on top
       of the standard bitmap controls because the PDF's raster
       regions still go through the same segmentation pipeline. The
       Hershey text re-render card sits at the very top of the
       document case so the operator's first reflex on "I want to
       plot this PDF" lands on the toggle that makes the text
       legible. -->
  <section v-else-if="fm.showsBitmapForm.value" class="space-y-3">
    <TypographyCard
      v-if="fm.kind.value === 'document'"
      :typo="draft.typo.value"
      :fonts="fonts"
      mode="document"
    />
    <BlockMapCard v-if="fm.kind.value === 'document'" />

    <ColorModeCard :mode="printMode" @update:mode="(mode) => draft.setPrintMode(mode)" />

    <template v-if="printMode === 'monochrome'">
      <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
        <PenSlotPicker
          :model-value="draft.monoPenSlot.value"
          @update:model-value="(v) => (draft.monoPenSlot.value = v)"
        />

        <MasterStylePicker
          :model-value="draft.monoMasterStyleId.value"
          @update:model-value="onMasterStyleChange"
        />

        <MasterStyleParams :bitmap="bitmap" :style-id="draft.monoMasterStyleId.value" />

        <p
          class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400"
        >
          {{ t('mono.layersHint') }}
        </p>
      </div>
    </template>

    <template v-else>
      <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
        <MasterStylePicker
          mode="multicolor"
          :model-value="draft.multicolorMasterStyleId.value"
          @update:model-value="onMulticolorMasterStyleChange"
        />

        <MultiColorMasterStyleParams
          :bitmap="bitmap"
          :style-id="draft.multicolorMasterStyleId.value"
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

  <p v-else class="text-[11px] text-slate-500">
    {{ t('style.notApplicable') }}
  </p>
</template>
