<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { useJobStore } from '../../../stores/job'
import ColorModeCard from '../colors/ColorModeCard.vue'
import PaletteCard from '../source/PaletteCard.vue'
import SegmentationCard from '../source/SegmentationCard.vue'

// Colors tab — "how many layers, what colours, how to split the
// image". Owns the multicolour vs monochrome toggle, the palette
// (manual / follows pens), and the segmentation method + its primary
// knobs (num_colors / num_bands / thresholds). The Render tab handles
// the per-style mono picker and global render knobs; the Layers tab
// the per-layer overrides.

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

// When palette-follows-pens is on AND there are installed pens, mirror
// them into the draft palette + lock the segmentation method to
// ``fixed_palette``. Guarded against stomping a mono-mode rehydrate:
// a placement uploaded with luminance_bands (mono shaded) would
// otherwise have its segmentation_method silently overwritten to
// fixed_palette the moment ColorsTab mounts with immediate=true, with
// the operator seeing a colourful preview for a single-ink placement.
// The guard `printMode === 'multicolor'` keeps seeding behaviour for
// genuine multicolour placements without polluting mono ones.
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
</script>

<template>
  <section v-if="fm.hasSource.value && fm.showsBitmapForm.value" class="space-y-3">
    <ColorModeCard :mode="printMode" @update:mode="(mode) => draft.setPrintMode(mode)" />

    <template v-if="printMode === 'multicolor'">
      <PaletteCard
        :bitmap="bitmap"
        :palette-follows-pens="draft.paletteFollowsPens.value"
        :installed-pen-colors="installedPenColors"
        :pen-slot-count="penSlotCount"
        :manual-swap-count="manualSwapCount"
        @update:palette-follows-pens="setPaletteFollowsPens"
      />
      <SegmentationCard :bitmap="bitmap" :is-document="fm.kind.value === 'document'" />
    </template>

    <p
      v-else
      class="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-[11px] text-slate-400"
    >
      {{ t('colors.monoHint') }}
    </p>
  </section>

  <p
    v-else-if="!fm.hasSource.value"
    class="text-[11px] text-slate-500"
  >
    {{ t('colors.noSource') }}
  </p>

  <p
    v-else
    class="text-[11px] text-slate-500"
  >
    {{ t('colors.notApplicable') }}
  </p>
</template>
