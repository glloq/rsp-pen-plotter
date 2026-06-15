// Shared sheet-outline geometry contract for the V2 editor preview.
//
// Lifted out of ``EditPreviewPane.vue`` so the geometry composable
// (``useEditorPreviewSheetGeometry``) can reference the shape without importing
// the component (which would be circular). ``EditPreviewPane.vue`` re-exports
// this type for backwards compatibility with existing callers.

export interface SheetOutlineShape {
  // Real aspect ratio (w/h) — fed straight to CSS ``aspect-ratio`` so the
  // rectangle keeps its shape regardless of how wide vs. tall the preview pane
  // is. Percent-of-axis sizing distorted the shape on non-square panes; that
  // bug is what this interface fixes.
  aspectRatio: number
  labelW: number
  labelH: number
  isPortrait: boolean
  /** Real sheet width in mm — used to scale the artwork so the same drawing
   *  visibly shrinks when the operator picks a bigger paper format (and
   *  overflows when picking a smaller one). */
  widthMm: number
  /** Real sheet height in mm — companion to ``widthMm``. */
  heightMm: number
}
