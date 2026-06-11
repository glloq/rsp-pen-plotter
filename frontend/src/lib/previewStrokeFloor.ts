// Display-time stroke floor for the editor preview.
//
// The rendered SVG carries true-to-life stroke widths (the physical pen
// tip converted into viewBox units). Physically correct — but a 0.5 mm
// pen on an 800 px raster shown inside a ~350 px pane lands well below
// one device pixel, and the browser's anti-aliasing renders sub-pixel
// strokes as pale, washed-out tints ("is there transparency on the
// preview?" — no, just hairlines). This helper floors each stroke at a
// minimum on-screen width so colours stay readable at fit zoom, while
// zooming in past the floor restores the exact physical widths.
//
// Purely cosmetic: it mutates the *displayed* DOM only, never the SVG
// string that flows to /generate.

/** Minimum on-screen stroke width (device px) for preview readability. */
export const MIN_DISPLAY_STROKE_PX = 0.8

const ORIGINAL_ATTR = 'data-original-stroke-width'

/**
 * Floor every ``stroke-width`` in ``svg`` so it renders at least
 * ``minDisplayPx`` device pixels given the element's current on-screen
 * width. Idempotent: the first pass stashes each element's true width
 * in a data attribute and later passes recompute from it, so repeated
 * calls (zoom changes, re-renders) never compound.
 *
 * ``displayWidthPx`` is the svg's rendered width in device pixels
 * (``getBoundingClientRect().width`` — includes any CSS zoom
 * transform). No-ops when layout hasn't happened yet (width 0) or the
 * viewBox is missing.
 */
export function applyPreviewStrokeFloor(
  svg: SVGSVGElement,
  displayWidthPx: number,
  minDisplayPx: number = MIN_DISPLAY_STROKE_PX,
): void {
  if (!displayWidthPx || displayWidthPx <= 0) return
  const viewBox = svg.getAttribute('viewBox')
  if (!viewBox) return
  const parts = viewBox.trim().split(/[\s,]+/).map(Number)
  const vbWidth = parts[2]
  if (!vbWidth || !Number.isFinite(vbWidth) || vbWidth <= 0) return
  // viewBox units that correspond to one device pixel at the current
  // display scale; the floor expressed in viewBox units.
  const floor = minDisplayPx * (vbWidth / displayWidthPx)
  const elements = svg.querySelectorAll<SVGElement>('[stroke-width]')
  for (const el of Array.from(elements)) {
    let original = el.getAttribute(ORIGINAL_ATTR)
    if (original === null) {
      original = el.getAttribute('stroke-width')
      if (original === null) continue
      el.setAttribute(ORIGINAL_ATTR, original)
    }
    const value = Number(original)
    if (!Number.isFinite(value)) continue
    const next = Math.max(value, floor)
    el.setAttribute('stroke-width', String(next))
  }
}
