<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getFonts } from '../../../api/client'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { useJobStore } from '../../../stores/job'
import { useToastStore } from '../../../stores/toasts'
import BlockMapCard from '../BlockMapCard.vue'
import ColorModeCard from '../colors/ColorModeCard.vue'
import MasterStylePicker from '../render/MasterStylePicker.vue'
import MasterStyleParams from '../render/MasterStyleParams.vue'
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
const toasts = useToastStore()

const bitmap = draft.bitmap
const printMode = draft.printMode

const installedPenColors = computed<string[]>(() => {
  const pens = store.selectedProfile?.pens ?? []
  return pens.filter((p) => p.installed && p.color).map((p) => p.color)
})

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

// When palette-follows-pens is on AND there are installed pens, mirror
// them into the draft palette + lock the segmentation method to
// ``fixed_palette``. Guarded against stomping a mono-mode rehydrate
// (see ColorsTab's original comment) — only seed for genuine
// multicolour placements.
watch(
  [draft.paletteFollowsPens, installedPenColors],
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
  try { fonts.value = await getFonts() } catch { /* keep [] */ }
})

// Switching master style: rewrite the draft's segmentation + uniform
// algorithm via the centralised helper, then surface a toast if the
// operator had manually tweaked the segmentation knobs (so the silent
// stomp class of bug is gone). When layers already exist (post-upload),
// also re-propagate the per-band recipe across them so the live preview
// reflects the new style without needing a re-upload. If the operator
// has overridden some layers manually, confirm before stomping.
async function onMasterStyleChange(id: string): Promise<void> {
  const previous = draft.monoMasterStyleId.value
  const overwritten = draft.setMasterStyle(id)
  if (overwritten.length > 0) {
    toasts.warning(
      t('render.styleOverwroteFields', {
        fields: overwritten.map((f) => t(`render.field_${f}`)).join(', '),
      }),
    )
  }

  if (store.layers.length > 0 && previous !== id) {
    const overrideCount = Object.keys(store.layerAlgorithms).length
    if (overrideCount > 0) {
      const ok = window.confirm(
        t('render.replaceOverridesWarning', { count: overrideCount }),
      )
      if (!ok) return
    }
    await applyMasterStyleToLayers(store, {
      styleId: id,
      penSlot: draft.monoPenSlot.value,
    })
  }
}

// Multicolour twin of ``onMasterStyleChange`` — same warn-on-touched +
// post-upload propagation logic, just driving the multicolour master.
// Per-layer overrides survive across master switches identically to
// the mono case (operator gets the same window.confirm).
async function onMulticolorMasterStyleChange(id: string): Promise<void> {
  const previous = draft.multicolorMasterStyleId.value
  const overwritten = draft.setMulticolorMasterStyle(id)
  if (overwritten.length > 0) {
    toasts.warning(
      t('render.styleOverwroteFields', {
        fields: overwritten.map((f) => t(`render.field_${f}`)).join(', '),
      }),
    )
  }

  if (store.layers.length > 0 && previous !== id) {
    const overrideCount = Object.keys(store.layerAlgorithms).length
    if (overrideCount > 0) {
      const ok = window.confirm(
        t('render.replaceOverridesWarning', { count: overrideCount }),
      )
      if (!ok) return
    }
    // Multicolour styles don't have a target pen slot — each layer
    // already carries its own ``target_pen_slot`` from segmentation /
    // pen matching, so just push the default algorithm + options.
    await applyMasterStyleToLayers(store, { styleId: id, penSlot: null })
  }
}
</script>

<template>
  <!-- Typography source: dedicated card replaces the bitmap content. -->
  <section v-if="fm.kind.value === 'typography'" class="space-y-3">
    <TypographyCard :typo="draft.typo.value" :fonts="fonts" />
  </section>

  <!-- Bitmap or document (PDF). Document gets a BlockMapCard on top
       of the standard bitmap controls because the PDF's raster
       regions still go through the same segmentation pipeline. -->
  <section v-else-if="fm.showsBitmapForm.value" class="space-y-3">
    <BlockMapCard v-if="fm.kind.value === 'document'" />

    <ColorModeCard :mode="printMode" @update:mode="(mode) => draft.setPrintMode(mode)" />

    <template v-if="printMode === 'monochrome'">
      <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
        <PenSlotPicker
          :model-value="draft.monoPenSlot.value"
          @update:model-value="(v) => draft.monoPenSlot.value = v"
        />

        <MasterStylePicker
          :model-value="draft.monoMasterStyleId.value"
          @update:model-value="onMasterStyleChange"
        />

        <MasterStyleParams
          :bitmap="bitmap"
          :style-id="draft.monoMasterStyleId.value"
        />

        <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400">
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
      </div>

      <PaletteCard
        :bitmap="bitmap"
        :palette-follows-pens="draft.paletteFollowsPens.value"
        :installed-pen-colors="installedPenColors"
        :pen-slot-count="penSlotCount"
        :manual-swap-count="manualSwapCount"
        @update:palette-follows-pens="setPaletteFollowsPens"
      />
      <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400">
        {{ t('render.multicolorHint') }}
      </p>
    </template>

    <PostProcessCard :bitmap="bitmap" />
  </section>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('style.notApplicable') }}
  </p>
</template>
