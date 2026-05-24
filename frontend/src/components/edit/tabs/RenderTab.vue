<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { resolveMasterStyle } from '../../../data/printRegistry'
import { useJobStore } from '../../../stores/job'
import MasterStylePicker from '../render/MasterStylePicker.vue'
import MasterStyleParams from '../render/MasterStyleParams.vue'
import DetailPicker from '../shared/DetailPicker.vue'
import PenSlotPicker from '../shared/PenSlotPicker.vue'

// Render tab — "how should the layers actually be drawn?". For mono
// mode this is the master-style gallery + per-style knobs + pen slot
// + detail tier. For multicolour mode it shows the global detail
// picker and points the operator at the Layers tab for per-layer
// render choices (which is where multicolour rendering actually
// happens).

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)
const store = useJobStore()

const printMode = draft.printMode

// Switching master style: rewrite the draft's segmentation + uniform
// algorithm (same logic ``MonochromeCard.selectMode`` used). When
// layers already exist (post-upload), also re-propagate the per-band
// recipe across them so the live preview reflects the new style
// without needing a re-upload. If the operator has overridden some
// layers manually, confirm before stomping their work.
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

  // Re-propagate to existing layers (post-upload only). Confirm if
  // the operator already overrode some layers — we'd otherwise stomp
  // their tuning silently.
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
  <section v-if="fm.hasSource.value && fm.showsBitmapForm.value" class="space-y-3">
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
           the detail tier, which controls segmentation resolution and
           applies to every layer the same way. -->
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

  <p v-else-if="!fm.hasSource.value" class="text-[11px] text-slate-500">
    {{ t('render.noSource') }}
  </p>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('render.notApplicable') }}
  </p>
</template>
