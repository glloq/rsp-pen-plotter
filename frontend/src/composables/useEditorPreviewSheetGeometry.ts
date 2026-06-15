// Sheet + artwork geometry for the V2 editor preview pane.
//
// Extracted from ``EditPreviewPane.vue`` (Phase 4 of the editor audit). Owns
// the pane's pixel-size tracking (ResizeObserver) and the pure geometry that
// fits the dashed sheet rectangle into the pane at its real aspect ratio and
// sizes the artwork box as a fraction of that sheet (artworkMm / sheetMm).
// Kept as a composable so the fit/clamp maths is testable by injecting
// ``paneWidth`` / ``paneHeight`` instead of mounting the pane and faking a
// ResizeObserver.
import { computed, getCurrentInstance, onMounted, onScopeDispose, ref } from 'vue'
import type { SheetOutlineShape } from '../components/v2/sheetGeometry'

export interface EditorPreviewSheetGeometryDeps {
  /** Active sheet outline geometry, or null when no sheet is selected. */
  sheet: () => SheetOutlineShape | null
  /** Artwork's physical width in mm, or null/undefined when unknown. */
  artworkWidthMm: () => number | null | undefined
  /** Artwork's physical height in mm, or null/undefined when unknown. */
  artworkHeightMm: () => number | null | undefined
}

export function useEditorPreviewSheetGeometry(deps: EditorPreviewSheetGeometryDeps) {
  // Template ref bound to the pane element; the ResizeObserver watches it.
  const paneEl = ref<HTMLElement | null>(null)
  const paneWidth = ref(0)
  const paneHeight = ref(0)
  let paneObserver: ResizeObserver | null = null

  // CSS ``aspect-ratio`` alone won't fit a rectangle into a non-square pane
  // without distortion — when both axes are constrained, the browser picks
  // one and the aspect breaks. We track the pane's real pixel size, then
  // derive the sheet's width/height in pixels so it's *guaranteed* to honour
  // the requested aspect ratio AND fit inside 92 % of the pane on whichever
  // axis is tighter.
  const sheetStyle = computed<{ width: string; height: string } | null>(() => {
    const s = deps.sheet()
    if (!s) return null
    const ratio = s.aspectRatio
    if (!Number.isFinite(ratio) || ratio <= 0) return null
    const pw = paneWidth.value
    const ph = paneHeight.value
    if (pw <= 0 || ph <= 0) return null
    const maxW = pw * 0.92
    const maxH = ph * 0.92
    // Anchor on whichever axis caps the rectangle first. ``maxW / ratio`` is
    // the height the rectangle would take if it filled maxW; if that exceeds
    // maxH, the sheet is taller than it is wide and we anchor on height.
    let w: number
    let h: number
    if (maxW / ratio <= maxH) {
      w = maxW
      h = maxW / ratio
    } else {
      h = maxH
      w = maxH * ratio
    }
    return { width: `${Math.round(w)}px`, height: `${Math.round(h)}px` }
  })

  // Artwork-inside-sheet sizing. Sizes the artwork as a fraction of the sheet
  // (artworkMm / sheetMm) so a 100 × 100 mm drawing visibly fills half of an
  // A4 portrait (210 × 297 mm) and barely covers a quarter of A3. Falls back
  // to "fill the sheet" when the artwork's own dimensions aren't known yet
  // (typically during the first /preview round-trip on upload).
  const artworkFraction = computed<{ w: number; h: number } | null>(() => {
    const sheet = deps.sheet()
    if (!sheet) return null
    const sw = sheet.widthMm
    const sh = sheet.heightMm
    if (!sw || !sh) return null
    const aw = deps.artworkWidthMm() ?? sw
    const ah = deps.artworkHeightMm() ?? sh
    let w = aw / sw
    let h = ah / sh
    // Overflow clamp: scale BOTH axes by the same factor so an artwork bigger
    // than the sheet still keeps its aspect ratio while filling the page. A
    // per-axis ``Math.min(100, …)`` clamp stretched the drawing whenever the
    // two axes overflowed by different amounts (e.g. an A4-sized artwork on
    // an A6 sheet).
    const over = Math.max(w, h)
    if (over > 1) {
      w /= over
      h /= over
    }
    return { w, h }
  })

  const artworkStyle = computed<{ width: string; height: string } | null>(() => {
    // Express the artwork box as a percentage of the sheet so the inline
    // sheet container (already sized in pixels by ``sheetStyle``) does the
    // unit conversion for us.
    const f = artworkFraction.value
    if (!f) return null
    return { width: `${f.w * 100}%`, height: `${f.h * 100}%` }
  })

  // Lifecycle is component-only (it needs the mounted DOM ref); guard on the
  // instance so the geometry computeds stay unit-testable standalone.
  if (getCurrentInstance()) {
    onMounted(() => {
      if (!paneEl.value || typeof ResizeObserver === 'undefined') return
      paneObserver = new ResizeObserver((entries) => {
        const entry = entries[0]
        if (!entry) return
        const rect = entry.contentRect
        paneWidth.value = rect.width
        paneHeight.value = rect.height
      })
      paneObserver.observe(paneEl.value)
    })
    onScopeDispose(() => {
      paneObserver?.disconnect()
      paneObserver = null
    })
  }

  return { paneEl, paneWidth, paneHeight, sheetStyle, artworkFraction, artworkStyle }
}
