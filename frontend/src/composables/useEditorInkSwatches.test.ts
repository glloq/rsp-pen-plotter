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

  it('expert mode: always snaps live centroids onto the nearest available ink', () => {
    useUiModeStore().setMode('expert')
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([{ color: '#cc2020' }, { color: '#20cc20' }]),
      effectivePool: ref(['#ff0000', '#00ff00']),
    })
    expect(previewInkSnap.value).not.toBeNull()
    // #cc2020 (red) → red ; #20cc20 (green) → green. Always snapped, whatever
    // the segmentation method or palette-source toggle.
    expect(previewInkSnap.value!.map.get('#cc2020')).toBe('#ff0000')
    expect(previewInkSnap.value!.map.get('#20cc20')).toBe('#00ff00')
    expect(inkSwatches.value.map((s) => s.hex)).toEqual(['#ff0000', '#00ff00'])
  })

  it('expert mode: a kmeans cluster snaps to an AVAILABLE ink, never its raw centroid', () => {
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.bitmap.value.segmentation_method = 'kmeans'
    draft.paletteFollowsPens.value = false
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      // A green cluster the image produced (not equal to any inventory ink).
      fileManager: fileManagerWith([{ color: '#3aa85a' }]),
      // Inventory: blue + two greens.
      effectivePool: ref(['#1e1edc', '#22aa55', '#0e7a3a']),
    })
    const hex = inkSwatches.value[0]!.hex
    // The chip shows one of the GREEN inventory inks, not the raw centroid
    // (#3aa85a) — the "couleur hors liste sous la preview" bug.
    expect(['#22aa55', '#0e7a3a']).toContain(hex)
    expect(hex).not.toBe('#3aa85a')
    expect(previewInkSnap.value!.map.get('#3aa85a')).toBe(hex)
  })

  it('expert mode: a MANUAL layer override wins; the rest snap to the pool', () => {
    seedPlacement() // 2 committed layers: ddeeff(draw 0), aabbcc(draw 1)
    useUiModeStore().setMode('expert')
    const job = useJobStore()
    const firstLayerId = [...(job.selectedPlacement?.layers ?? [])].sort(
      (a, b) => a.draw_order - b.draw_order,
    )[0]!.layer_id
    job.updateLayer(firstLayerId, {
      assigned_color_hex: '#abcdef',
      color_assignment: 'manual',
    })
    // Live palette has 2 clusters = 2 committed layers, so they're ALIGNED and
    // the manual override is honoured.
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([{ color: '#111111' }, { color: '#222222' }]),
      effectivePool: ref(['#ff0000', '#00ff00']),
    })
    expect(previewInkSnap.value!.map.get('#111111')).toBe('#abcdef')
    // The second cluster is auto-snapped onto an owned ink (not left raw).
    expect(['#ff0000', '#00ff00']).toContain(previewInkSnap.value!.map.get('#222222'))
    expect(inkSwatches.value[0]!.hex).toBe('#abcdef')
    expect(inkSwatches.value[0]!.layerId).toBe(firstLayerId)
  })

  it('expert mode: a changed colour count ignores stale layers and snaps from live centroids', () => {
    seedPlacement() // 2 committed layers
    useUiModeStore().setMode('expert')
    // The operator raised num_colors → the live preview now has 3 clusters,
    // which no longer match the 2 committed layers. No stale layer colour may
    // leak in (the "blue for green / grey for green" bug); each cluster snaps
    // purely from its own live centroid.
    const { previewInkSnap, inkSwatches } = useEditorInkSwatches({
      fileManager: fileManagerWith([
        { color: '#2b2b2b' },
        { color: '#3aa85a' },
        { color: '#4a4ad8' },
      ]),
      effectivePool: ref(['#111111', '#22aa55', '#1e1edc']),
    })
    expect(inkSwatches.value).toHaveLength(3)
    // dark grey → black, green → green, blue → blue.
    expect(inkSwatches.value.map((s) => s.hex)).toEqual(['#111111', '#22aa55', '#1e1edc'])
    // None of the chips are wired to a stale committed layer.
    expect(inkSwatches.value.every((s) => s.layer === null)).toBe(true)
    expect(previewInkSnap.value!.map.get('#3aa85a')).toBe('#22aa55')
  })
})
