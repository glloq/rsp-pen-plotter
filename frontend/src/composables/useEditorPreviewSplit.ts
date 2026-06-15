// Compare (split) slider for the V2 editor preview pane.
//
// Extracted from ``EditPreviewPane.vue`` (Phase 4 of the editor audit). Owns
// the draggable vertical handle that sweeps the source ↔ result reveal in
// "Compare" mode, plus the clip-paths that realise it. Kept as a composable
// so the handle maths (sheet-space pointer → artwork-space clip) is testable
// without mounting the pane.
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'

export interface EditorPreviewSplitDeps {
  /** The pane's active view mode — the slider only lives in 'split'. */
  viewMode: Ref<'plot' | 'source' | 'split'>
  /** Artwork size as a fraction of the sheet (w/h in 0..1), or null when
   *  the artwork fills the sheet. Used to convert the handle's sheet-space
   *  position into the artwork-space clip the SVG layers actually use. */
  artworkFraction:
    | Ref<{ w: number; h: number } | null>
    | ComputedRef<{ w: number; h: number } | null>
}

export function useEditorPreviewSplit(deps: EditorPreviewSplitDeps) {
  const splitPercent = ref<number>(50)
  const splitDragging = ref<boolean>(false)
  // We measure against the SHEET, not the pane, because the handle's
  // ``left: ${splitPercent}%`` is relative to the sheet outline (which is
  // what contains the artwork). Using the pane rect made the handle jump
  // under the pointer when the sheet wasn't pane-wide.
  let splitSheetRect: DOMRect | null = null

  function updateSplit(event: PointerEvent): void {
    if (!splitSheetRect) return
    const x = event.clientX - splitSheetRect.left
    const pct = (x / splitSheetRect.width) * 100
    splitPercent.value = Math.max(0, Math.min(100, pct))
  }
  function onSplitGrab(event: PointerEvent): void {
    const sheet = (event.currentTarget as HTMLElement).closest(
      '.sheet-outline',
    ) as HTMLElement | null
    if (!sheet) return
    event.stopPropagation()
    event.preventDefault()
    splitDragging.value = true
    splitSheetRect = sheet.getBoundingClientRect()
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
    updateSplit(event)
  }
  function onSplitMove(event: PointerEvent): void {
    if (!splitDragging.value) return
    updateSplit(event)
  }
  function onSplitRelease(event: PointerEvent): void {
    if (!splitDragging.value) return
    splitDragging.value = false
    splitSheetRect = null
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  }

  // Reset to 50/50 when switching INTO split mode so the operator gets a
  // clean fresh sweep instead of inheriting wherever the last drag ended
  // (often 0 % or 100 %, which hides one side entirely).
  watch(deps.viewMode, (next, prev) => {
    if (next === 'split' && prev !== 'split') splitPercent.value = 50
  })

  // Clip-paths for split mode: the plot SVG is revealed from the right edge
  // inward to ``splitPercent``; the source SVG fills the complementary left
  // band. The handle's ``left`` is a percentage of the SHEET, but the clips
  // apply to the artwork layers inside the (top-left anchored, possibly
  // smaller) artwork box — so convert from sheet space into artwork space
  // first, else the cut line drifts from the handle on oversized formats.
  const splitArtworkPercent = computed<number>(() => {
    const f = deps.artworkFraction.value
    if (!f || f.w <= 0) return splitPercent.value
    return Math.max(0, Math.min(100, splitPercent.value / f.w))
  })
  const splitPlotClip = computed<string>(() => `inset(0 0 0 ${splitArtworkPercent.value}%)`)
  const splitSourceClip = computed<string>(() => `inset(0 ${100 - splitArtworkPercent.value}% 0 0)`)

  return {
    splitPercent,
    splitDragging,
    onSplitGrab,
    onSplitMove,
    onSplitRelease,
    splitPlotClip,
    splitSourceClip,
  }
}
