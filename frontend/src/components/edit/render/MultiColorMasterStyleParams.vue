<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveMulticolorStyle } from '../../../data/printRegistry'
import { useBitmapDraft, type MulticolorStyleKnobs } from '../../../composables/useBitmapDraft'
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

// Push the updated knobs onto existing layers so /rerender (gcode
// generation) reflects the slider change. /preview ships ``band_recipes``
// computed fresh from knobs and works without this, but the persisted
// ``layer_algorithms`` would otherwise stay on the values captured at
// upload time — the editor preview and the gcode output would diverge as
// soon as the operator tweaks any knob (crossed, angle_step, spacing
// range, …).
function propagateKnobsToLayers(): Promise<number> {
  return applyMasterStyleToLayers(store, {
    styleId: props.styleId,
    penSlot: null,
    recipeResolver: (index, total, hex) => draft.multicolorRecipeForCluster(index, total, hex),
  })
}

function setKnob(key: string, value: unknown): void {
  // Data-driven knob editor: ``MasterStyleKnobs`` emits ``(string, unknown)``
  // since the field name isn't statically known. Narrow only the key + value
  // crossing this boundary instead of widening the setter to ``any`` (which
  // would drop type-checking from every other call site).
  draft.setMulticolorKnob(props.styleId, key as keyof MulticolorStyleKnobs, value as never)
  if (store.layers.length > 0) {
    if (knobPropagationTimer !== null) clearTimeout(knobPropagationTimer)
    knobPropagationTimer = setTimeout(() => {
      knobPropagationTimer = null
      void propagateKnobsToLayers()
    }, KNOB_PROPAGATION_DELAY_MS)
  }
}

// Drain the trailing-edge propagation timer immediately. Registered as a
// store flush hook so /preflight + /generate apply the operator's last
// knob tweak before reading ``placement.svg`` — otherwise hitting
// Generate within the 120ms debounce window emitted the previous style.
async function flushPendingKnobPropagation(): Promise<void> {
  if (knobPropagationTimer === null) return
  clearTimeout(knobPropagationTimer)
  knobPropagationTimer = null
  await propagateKnobsToLayers()
}

let unregisterFlushHook: (() => void) | null = null
onMounted(() => {
  unregisterFlushHook = store.registerRerenderFlushHook(flushPendingKnobPropagation)
})
onBeforeUnmount(() => {
  unregisterFlushHook?.()
  unregisterFlushHook = null
  if (knobPropagationTimer !== null) clearTimeout(knobPropagationTimer)
})
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
