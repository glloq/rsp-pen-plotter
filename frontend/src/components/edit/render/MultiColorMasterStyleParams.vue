<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMulticolorStyle } from '../../../data/printRegistry'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { applyMasterStyleToLayers } from '../../../composables/useStylePropagation'
import { useJobStore } from '../../../stores/job'
import MasterStyleKnobs from './MasterStyleKnobs.vue'

// Per-style operator knobs for the multicolour master family — sibling
// of ``MasterStyleParams.vue`` but for the colour-recipe pipeline. The
// per-style knob UI is declarative (``data/styleKnobs.ts`` descriptors
// rendered by the shared ``MasterStyleKnobs`` component), so a new
// colour master needs zero edits here. The cluster-count slider moved
// to the sibling ``ColorCountSlider.vue`` so the Style tab can show it
// before the master-style picker (colour count first, then style).

const props = defineProps<{
  styleId: string
  /**
   * Smallest pen tip diameter (mm) among the colours this style draws
   * with — floors the physical mark knobs (``dot_radius``,
   * ``stroke_width``) at the thinnest mark any installed pen can make.
   */
  minPenWidthMm?: number | null
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
</script>

<template>
  <div class="space-y-3">
    <!-- ===== Per-style knob block — declarative (data/styleKnobs.ts) ===== -->
    <MasterStyleKnobs
      family="multicolor"
      :style-id="styleId"
      :knobs="knobs"
      :min-pen-width-mm="minPenWidthMm"
      @set="setKnob"
    />

    <p class="text-[10px] text-slate-500">
      {{ style.descriptionKey ? t(style.descriptionKey) : '' }}
    </p>
  </div>
</template>
