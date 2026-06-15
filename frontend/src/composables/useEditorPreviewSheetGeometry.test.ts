import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useEditorPreviewSheetGeometry } from './useEditorPreviewSheetGeometry'
import type { SheetOutlineShape } from '../components/v2/sheetGeometry'

// Portrait A4.
const A4: SheetOutlineShape = {
  aspectRatio: 210 / 297,
  labelW: 210,
  labelH: 297,
  isPortrait: true,
  widthMm: 210,
  heightMm: 297,
}

// The lifecycle (ResizeObserver wiring) is component-only and guarded on
// getCurrentInstance, so calling the composable standalone exercises only the
// pure geometry computeds. We drive pane size by writing the returned refs.
function setup(sheet: SheetOutlineShape | null, artworkWidthMm = 105, artworkHeightMm = 148.5) {
  const sheetRef = ref<SheetOutlineShape | null>(sheet)
  const aw = ref<number | null>(artworkWidthMm)
  const ah = ref<number | null>(artworkHeightMm)
  const geom = useEditorPreviewSheetGeometry({
    sheet: () => sheetRef.value,
    artworkWidthMm: () => aw.value,
    artworkHeightMm: () => ah.value,
  })
  return { geom, sheetRef, aw, ah }
}

describe('useEditorPreviewSheetGeometry', () => {
  it('returns null geometry until the pane has been measured', () => {
    const { geom } = setup(A4)
    // paneWidth / paneHeight start at 0 — no ResizeObserver has fired.
    expect(geom.sheetStyle.value).toBeNull()
    // Artwork fraction is pure mm maths, available immediately.
    expect(geom.artworkStyle.value).toEqual({ width: '50%', height: '50%' })
  })

  it('anchors the sheet on width when the pane is relatively tall', () => {
    const { geom } = setup(A4)
    // 800 × 1200 pane: 0.92 width = 736; height it would need = 736 / (210/297)
    // = 1041 < 0.92*1200 = 1104, so the rectangle is width-anchored.
    geom.paneWidth.value = 800
    geom.paneHeight.value = 1200
    expect(geom.sheetStyle.value).toEqual({ width: '736px', height: '1041px' })
  })

  it('anchors the sheet on height when the pane is relatively wide', () => {
    const { geom } = setup(A4)
    // 1200 × 600 pane: width-anchored height would be 1104 / (210/297) = 1561 >
    // 0.92*600 = 552, so it flips to height-anchored: h = 552, w = 552*210/297.
    geom.paneWidth.value = 1200
    geom.paneHeight.value = 600
    expect(geom.sheetStyle.value).toEqual({ width: '390px', height: '552px' })
  })

  it('clamps an oversized artwork uniformly so its aspect ratio survives', () => {
    // 420 × 297 on a 210 × 297 sheet: width overflows 2×, height fits. A
    // per-axis clamp would stretch to 100 % × 100 %; the uniform clamp keeps
    // the shape → 100 % × 50 %.
    const { geom } = setup(A4, 420, 297)
    expect(geom.artworkStyle.value).toEqual({ width: '100%', height: '50%' })
  })

  it('fills the sheet when artwork dimensions are unknown', () => {
    const { aw, ah, geom } = setup(A4)
    aw.value = null
    ah.value = null
    expect(geom.artworkStyle.value).toEqual({ width: '100%', height: '100%' })
  })

  it('yields null fractions and style when no sheet is selected', () => {
    const { geom } = setup(null)
    geom.paneWidth.value = 800
    geom.paneHeight.value = 600
    expect(geom.sheetStyle.value).toBeNull()
    expect(geom.artworkFraction.value).toBeNull()
    expect(geom.artworkStyle.value).toBeNull()
  })

  it('rejects a degenerate aspect ratio', () => {
    const { geom } = setup({ ...A4, aspectRatio: 0 })
    geom.paneWidth.value = 800
    geom.paneHeight.value = 600
    expect(geom.sheetStyle.value).toBeNull()
  })
})
