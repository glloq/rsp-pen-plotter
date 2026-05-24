<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import MonochromeCard from '../source/MonochromeCard.vue'
import DetailPicker from '../shared/DetailPicker.vue'

// Render tab — "how should the layers actually be drawn?". For mono
// mode it hosts the master-style picker (Pencil / Halftone /
// Stippling / Engraving / Contours / Outline / TSP / Spiral) plus
// the per-style pen + bands/threshold knobs. For multicolor mode it
// shows a global detail picker and points the operator at the Layers
// tab for per-layer render choices (which is where multicolour
// rendering actually happens).

const { t } = useI18n()
const draft = useBitmapDraft()
const fm = useFileManager(t)

const printMode = draft.printMode

function setMonoPenSlot(value: number): void {
  draft.monoPenSlot.value = value
}
function setMonoModeId(value: string): void {
  draft.monoMasterStyleId.value = value
}
</script>

<template>
  <section v-if="fm.hasSource.value && fm.showsBitmapForm.value" class="space-y-3">
    <MonochromeCard
      v-if="printMode === 'monochrome'"
      :bitmap="draft.bitmap.value"
      :mono-pen-slot="draft.monoPenSlot.value"
      :mono-mode-id="draft.monoMasterStyleId.value"
      @update:mono-pen-slot="setMonoPenSlot"
      @update:mono-mode-id="setMonoModeId"
    />

    <template v-else>
      <!-- Multicolor rendering is per-layer (see Layers tab). The only
           global render knob that still makes sense at this level is
           the detail tier, which controls segmentation resolution and
           applies to every layer the same way. -->
      <DetailPicker
        :model-value="draft.bitmap.value.max_dimension_px"
        @update:model-value="(v) => draft.bitmap.value.max_dimension_px = v"
      />
      <p class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400">
        {{ t('render.multicolorHint') }}
      </p>
    </template>
  </section>

  <p v-else-if="!fm.hasSource.value" class="text-[11px] text-slate-500">
    {{ t('render.noSource') }}
  </p>

  <p v-else class="text-[11px] text-slate-500">
    {{ t('render.notApplicable') }}
  </p>
</template>
