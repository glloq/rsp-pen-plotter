// Recolour a /preview SVG so each cluster is drawn in the pool ink it
// snaps to, instead of its raw segmentation centroid.
//
// The expert live-preview ships no ``ink_pool``, so the backend renders
// every cluster in its centroid colour. The ink chips, however, snap
// those centroids onto the operator's pool (greedy-unique ΔE) to show the
// inks that will actually be drawn. Without recolouring the SVG the
// preview shows the photo's own colours while the chip strip lists only a
// handful of pens — the "preview has more colours than listed" mismatch.
// Feeding the same centroid → ink map through this function makes the
// preview agree with the chips and the eventual print.

/**
 * Rewrite every ``fill``/``stroke`` hex in ``svg`` using ``map`` (keys
 * lowercased centroid hex → target ink hex).
 *
 * Single-pass replace keyed on the ORIGINAL matched token, so a centroid
 * that maps onto another centroid's value can't be re-mapped twice.
 * Colours absent from the map (e.g. a white paper rect, or fallback
 * clusters mapped to themselves) pass through untouched.
 */
export function recolorPreviewSvg(svg: string, map: Map<string, string>): string {
  if (map.size === 0) return svg
  return svg.replace(/(fill|stroke)="(#[0-9a-fA-F]{3,8})"/g, (whole, attr, hex) => {
    const to = map.get((hex as string).toLowerCase())
    return to ? `${attr}="${to}"` : whole
  })
}
