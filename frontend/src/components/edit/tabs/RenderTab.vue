<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getFonts } from '../../../api/client'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { resolveMasterStyle } from '../../../data/printRegistry'
import { useJobStore } from '../../../stores/job'
import MasterStylePicker from '../render/MasterStylePicker.vue'
import MasterStyleParams from '../render/MasterStyleParams.vue'
import DetailPicker from '../shared/DetailPicker.vue'
import PenSlotPicker from '../shared/PenSlotPicker.vue'
import TypographyCard from '../source/TypographyCard.vue'
import BlockMapCard from '../BlockMapCard.vue'

// Render tab — "how should the layers actually be drawn?". Three
// content shapes depending on the source kind:
//   - bitmap mono   → master-style gallery + per-style knobs + pen
//                     slot + detail tier
//   - bitmap multi  → DetailPicker + pointer to the Layers tab where
//                     per-layer rendering happens
//   - typography    → TypographyCard (font, size, line spacing,
//                     alignment, page geometry)
//   - document/PDF  → BlockMapCard + bitmap mono/multi knobs (PDF
//                     pages get rasterised so the bitmap controls
//                     still apply to the raster portion)
//
// The Source tab no longer exists, so TypographyCard / BlockMapCard
// live here now — they're conceptually "the render style for this
// source kind".

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const store = useJobStore()

const printMode = draft.printMode

// Font catalogue for TypographyCard (.txt / .md sources). Local to
// this tab rather than the singleton because no other tab needs it.
const fonts = ref<string[]>([])
onMounted(async () => {
  try { fonts.value = await getFonts() } catch { /* keep [] */ }
})

// Switching master style: rewrite the draft's segmentation + uniform
// algorithm. When layers already exist (post-upload), also re-propagate
// the per-band recipe across them so the live preview reflects the new
// style without needing a re-upload. If the operator has overridden
// some layers manually, confirm before stomping their work.
async function onMasterStyleChange(id: string): Promise<void> {
  const previous = draft.monoMasterStyleId.value
  draft.monoMasterStyleId.value = id

  const style = resolveMasterStyle(id)
  const seg = style.segmentation
  if (seg) {
    draft.bitmap.value.segmentation_method = seg.method
    draft.bitmap.value.drop_background = seg.drop_background
    draft.bitmap.value.background_luminance = seg.background_luminance
    draft.bitmap.value.algorithm = style.defaultAlgorithm
    draft.bitmap.value.algorithm_options = { ...style.defaultAlgorithmOptions }
    if (seg.method === 'luminance_bands') {
      if (draft.bitmap.value.num_bands < 2 || draft.bitmap.value.num_bands > 6) {
        draft.bitmap.value.num_bands = seg.default_num_bands ?? 4
      }
    } else if (seg.method === 'thresholds') {
      draft.bitmap.value.thresholds = [seg.default_threshold ?? 0.5]
    }
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
          :bitmap="draft.bitmap.value"
          :style-id="draft.monoMasterStyleId.value"
        />

        <DetailPicker
          :model-value="draft.bitmap.value.max_dimension_px"
          @update:model-value="(v) => draft.bitmap.value.max_dimension_px = v"
        />

        <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1 text-[10px] leading-snug text-slate-400">
          {{ t('mono.layersHint') }}
        </p>
      </div>
    </template>

    <template v-else>
      <!-- Multicolor rendering is per-layer (see Layers tab). The only
           global render knob that still makes sense at this level is
           the detail tier. -->
      <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
        <DetailPicker
          :model-value="draft.bitmap.value.max_dimension_px"
          @update:model-value="(v) => draft.bitmap.value.max_dimension_px = v"
        />
        <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400">
          {{ t('render.multicolorHint') }}
        </p>
      </div>
    </template>
  </section>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('render.notApplicable') }}
  </p>
</template>
