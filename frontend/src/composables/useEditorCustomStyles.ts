// Custom-style stack for the V2 editor (assisted mode).
//
// Extracted from ``EditModalV2.vue`` (Phase 4 of the editor audit). Owns the
// optional escape hatch from the resolver's automatic algorithm pick: the
// operator's selection state, whether the panel even applies (bitmap sources
// only), the one-shot seed from the placement's committed ``layer_algorithms``,
// and the ``PolicyPass[]`` projection that drives /rerender + Generate. Kept as
// a composable so the seed + projection logic is testable without mounting the
// modal.
import { computed, ref, type Ref } from 'vue'
import type { PolicyPass, SourceKind } from '../domain/policy/schemas'
import {
  BEGINNER_STYLES,
  deriveBeginnerStack,
  type CustomStyleSelection,
} from '../components/v2/beginnerStyles'
import { useJobStore } from '../stores/job'

export interface EditorCustomStylesDeps {
  /** Active source kind — custom styles only apply to bitmap sources. */
  sourceKind: () => SourceKind
}

export function useEditorCustomStyles(deps: EditorCustomStylesDeps) {
  const job = useJobStore()

  // Empty stack = resolver wins (default experience). Non-empty stack = the
  // modal overrides ``decision.default_*``.
  const customStyles: Ref<CustomStyleSelection[]> = ref<CustomStyleSelection[]>([])
  const customStylesActive = computed<boolean>(() => customStyles.value.length > 0)

  // Custom styles really only make sense for bitmap sources — vectors and PDFs
  // route through dedicated pipelines (vector_passthrough, pdf_text_*) that
  // ignore raster algorithms. The panel is hidden outright for non-bitmap
  // kinds so the affordance never misleads.
  const canCustomizeStyles = computed<boolean>(
    () => deps.sourceKind() === 'bitmap_photo' || deps.sourceKind() === 'bitmap_illustration',
  )

  // Seed the stack from the placement's *committed* ``layer_algorithms`` so the
  // beginner panel reflects the style the operator already chose — in either
  // editor mode — instead of starting empty and letting the resolver silently
  // re-pick a different one (which also overwrote the saved style on confirm).
  // Runs once on open; no-op for non-bitmap kinds or when the committed style
  // has no beginner-catalogue equivalent.
  function seedCustomStylesFromCommitted(): void {
    if (!canCustomizeStyles.value) return
    const placement = job.selectedPlacement
    const firstLayerId = placement?.layers[0]?.layer_id
    if (!placement || !firstLayerId) return
    const seeded = deriveBeginnerStack(placement.layer_algorithms[firstLayerId])
    if (seeded.length) customStyles.value = seeded
  }

  // Build the PolicyPass[] the user's stack expresses. The full algorithm
  // option set keeps its registry defaults (see printRegistry.ts) and we only
  // override the primary knob's key — the entire contract of the "1 simple
  // knob per style" decision.
  const customPasses = computed<PolicyPass[]>(() =>
    customStyles.value.map((sel) => {
      const style = BEGINNER_STYLES.find((s) => s.id === sel.id)!
      return {
        algorithm: sel.id,
        algorithm_options: { [style.primaryKnob.optionKey]: sel.knobValue },
      }
    }),
  )

  return {
    customStyles,
    customStylesActive,
    canCustomizeStyles,
    customPasses,
    seedCustomStylesFromCommitted,
  }
}
