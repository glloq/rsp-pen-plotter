// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useEditorInkSwatches, type InkSwatchFileManager } from './useEditorInkSwatches'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useBitmapDraft } from './useBitmapDraft'
import { useJobStore } from '../stores/job'
import { useUiModeStore } from '../stores/uiMode'

function fileManagerWith(palette: { color: string }[] | null): InkSwatchFileManager {
  return { previewResult: ref(palette ? { palette } : null) }
}

function seedPlacement() {
  const job = useJobStore()
  const id = job.addEmptyPlacement()
  job.placements = job.placements.map((p) =>
    p.id === id
      ? {
          ...p,
          layers: [
            {
              layer_id: 'color-aabbcc',
              source_color: '#aabbcc',
              assigned_color_hex: '#112233',
              draw_order: 1,
              target_pen_slot: null,
              total_length_mm: 0,
              path_count: 0,
              bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
              optimize: true,
              simplify_tolerance_mm: 0,
              drawing_speed_mm_s: null,
              color_label: null,
              pause_before: 'auto',
              color_assignment: 'auto',
            },
            {
              layer_id: 'color-ddeeff',
              source_color: '#ddeeff',
              assigned_color_hex: null,
              draw_order: 0,
              target_pen_slot: null,
              total_length_mm: 0,
              path_count: 0,
              bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
              optimize: true,
              simplify_tolerance_mm: 0,
              drawing_speed_mm_s: null,
              color_label: null,
              pause_before: 'auto',
              color_assignment: 'auto',
            },
          ],
        }
      : p,
  )
  job.selectPlacement(id)
}

describe('useEditorInkSwatches', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('assisted mode: chips come from committed layers in draw order', () => {
    seedPlacement()
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith(null),
      effectivePool: ref(['#112233', '#445566']),
    })
    // Not expert → no live snap.
    expect(previewInkSnap.value).toBeNull()
    // Draw order: ddeeff (0) before aabbcc (1).
    expect(inkSwatches.value.map((s) => s.layerId)).toEqual(['color-ddeeff', 'color-aabbcc'])
    // The unassigned layer falls back; the assigned one shows its ink.
    expect(inkSwatches.value[0]).toMatchObject({ hex: '#ddeeff', isFallback: true })
    expect(inkSwatches.value[1]).toMatchObject({ hex: '#112233', isFallback: false })
  })

  it('labels chips with the inventory name when the hex matches', () => {
    seedPlacement()
    const colors = useAvailableColorsStore()
    colors.colors = [{ hex: '#112233', name: 'Midnight', coverage: 0 } as never]
    const { inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith(null),
      effectivePool: ref([]),
    })
    const assigned = inkSwatches.value.find((s) => s.hex === '#112233')!
    expect(assigned.displayName).toBe('Midnight')
    expect(assigned.displayHex).toBe('#112233')
  })

  it('expert mode + follow-pens: snaps live centroids onto the pool', () => {
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = true
    // Pens-follow only snaps when the method is the palette-driven
    // fixed_palette — kmeans/kmeans_lab render the image's own colours.
    draft.bitmap.value.segmentation_method = 'fixed_palette'
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([{ color: '#100000' }, { color: '#001000' }]),
      effectivePool: ref(['#ff0000', '#00ff00']),
    })
    expect(previewInkSnap.value).not.toBeNull()
    // Each centroid maps to its nearest pool ink, and chips reflect those.
    expect(previewInkSnap.value!.map.size).toBe(2)
    expect(inkSwatches.value).toHaveLength(2)
    expect(inkSwatches.value.every((s) => s.layerId.startsWith('preview-'))).toBe(true)
  })

  it('expert mode + faithful-to-image: identity map keeps the centroids', () => {
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    draft.bitmap.value.segmentation_method = 'kmeans'
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([{ color: '#123456' }]),
      effectivePool: ref(['#ff0000']),
    })
    // Empty map → recolour is a no-op; the chip keeps the image colour.
    expect(previewInkSnap.value!.map.size).toBe(0)
    expect(inkSwatches.value[0]!.hex).toBe('#123456')
  })

  it('expert mode: a MANUAL layer override recolours the cluster + its chip', () => {
    seedPlacement()
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    draft.bitmap.value.segmentation_method = 'kmeans'
    // The two seeded layers are in draw order ddeeff(0), aabbcc(1). The live
    // preview clusters map to them by index. Make the first a MANUAL pick.
    const job = useJobStore()
    const firstLayerId = [...(job.selectedPlacement?.layers ?? [])].sort(
      (a, b) => a.draw_order - b.draw_order,
    )[0]!.layer_id
    job.updateLayer(firstLayerId, {
      assigned_color_hex: '#abcdef',
      color_assignment: 'manual',
    })
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([{ color: '#111111' }, { color: '#222222' }]),
      effectivePool: ref(['#ff0000', '#00ff00']),
    })
    // First cluster (#111111) is remapped onto the manual ink; the second is
    // faithful to the image (kmeans), so it stays out of the map.
    expect(previewInkSnap.value!.map.get('#111111')).toBe('#abcdef')
    expect(previewInkSnap.value!.map.has('#222222')).toBe(false)
    // The chip shows the manual ink and is wired to the real layer so the
    // eye toggle + assign popover can act on it.
    expect(inkSwatches.value[0]!.hex).toBe('#abcdef')
    expect(inkSwatches.value[0]!.layerId).toBe(firstLayerId)
    expect(inkSwatches.value[0]!.layer).not.toBeNull()
  })
})
