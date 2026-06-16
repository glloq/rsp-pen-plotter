// @vitest-environment happy-dom
import { nextTick } from 'vue'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MachineProfile } from '../api/client'

// A library-backed placement must remember the footprint the operator left
// it at (a resize, or the editor's "fit to A5" sheet picker) so re-dropping
// the file restores that size instead of recomputing an auto-fit size. The
// detail is fetched via getLibraryFile; the SVG/bbox here are deliberately
// generic — the footprint memory is independent of the file type.
const SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="296" height="420" ' +
  'viewBox="0 0 296 420"><rect x="0" y="0" width="296" height="420" ' +
  'fill="none" stroke="black"/></svg>'

const getLibraryFile = vi.fn().mockResolvedValue({
  file_id: 'lib-1',
  source_file: 'photo.png',
  source_mime: 'image/png',
  rerenderable: false,
  svg: SVG,
  layers: [
    {
      layer_id: 'L1',
      source_color: '#000000',
      bbox: { x_min: 0, y_min: 0, x_max: 296, y_max: 420 },
    },
  ],
  upload_warnings: [],
  upload_metadata: {},
})

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, getLibraryFile: (id: string) => getLibraryFile(id) }
})

import { useJobStore } from './job'
import { useLibraryStore } from './library'

function makeProfile(): MachineProfile {
  return {
    name: 'Test A3',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 420 },
    origin: 'bottom_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 30,
    travel_speed_mm_s: 80,
    acceleration_mm_s2: 500,
    pen_lift_time_ms: 0,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function seedProfile(): void {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
}

describe('library placements remember their footprint', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    seedProfile()
  })

  it('restores a saved A5 footprint on drop instead of auto-fitting', async () => {
    const library = useLibraryStore()
    library.saveFileSettings('lib-1', {
      layer_algorithms: {},
      visibility: {},
      footprint_mm: { width_mm: 148, height_mm: 210 },
    })
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    const p = store.placements.find((pl) => pl.id === id)!
    expect(p.width_mm).toBeCloseTo(148, 3)
    expect(p.height_mm).toBeCloseTo(210, 3)
  })

  it('clamps a saved footprint larger than the bed, preserving aspect', async () => {
    const library = useLibraryStore()
    library.saveFileSettings('lib-1', {
      layer_algorithms: {},
      visibility: {},
      footprint_mm: { width_mm: 600, height_mm: 800 },
    })
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    const p = store.placements.find((pl) => pl.id === id)!
    // Usable area is 277 × 400 mm (A3 bed minus the 10 mm default margin);
    // 600 × 800 scales down by min(277/600, 400/800) = 0.4617.
    expect(p.width_mm).toBeCloseTo(277, 2)
    expect(p.height_mm).toBeCloseTo(369.33, 1)
  })

  it('persists the footprint after a resize so the next drop restores it', async () => {
    const store = useJobStore()
    const library = useLibraryStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    store.selectPlacement(id)
    store.setDrawing({ width_mm: 148, height_mm: 210 })
    await nextTick()
    expect(library.getFileSettings('lib-1')?.footprint_mm).toEqual({
      width_mm: 148,
      height_mm: 210,
    })
    // A second placement of the same file comes back at the resized size.
    const id2 = await store.createPlacementFromLibrary('lib-1')
    const p2 = store.placements.find((pl) => pl.id === id2)!
    expect(p2.width_mm).toBeCloseTo(148, 3)
    expect(p2.height_mm).toBeCloseTo(210, 3)
  })

  it('remembers the format chosen on an Edit-from-library draft', async () => {
    // The exact reported flow: edit an already-processed file from the
    // library (a hidden draft), pick A5 with the editor's format selector
    // (fitSelectedPlacementToSheet), then drag-drop the file from the
    // library. The draft is where the format is set, so its footprint must
    // be persisted — otherwise the drop recomputes a too-big auto-fit size.
    const store = useJobStore()
    const library = useLibraryStore()
    const draftId = await store.createPlacementFromLibrary('lib-1', undefined, {
      asDraft: true,
    })
    store.selectPlacement(draftId)
    store.fitSelectedPlacementToSheet({ width_mm: 148, height_mm: 210 })
    await nextTick()
    const saved = library.getFileSettings('lib-1')?.footprint_mm
    expect(saved).toBeTruthy()
    expect(saved!.width_mm).toBeCloseTo(148, 0)
    expect(saved!.height_mm).toBeCloseTo(210, 0)

    const dropId = await store.createPlacementFromLibrary('lib-1')
    const dropped = store.placements.find((pl) => pl.id === dropId)!
    expect(dropped.width_mm).toBeCloseTo(saved!.width_mm, 3)
    expect(dropped.height_mm).toBeCloseTo(saved!.height_mm, 3)
    // The bug was the drop coming back at the ~277 mm fit-to-workspace size.
    expect(dropped.width_mm).toBeLessThan(160)
  })

  it('reopening the editor on a sized file does not clobber its footprint', async () => {
    const store = useJobStore()
    const library = useLibraryStore()
    library.saveFileSettings('lib-1', {
      layer_algorithms: {},
      visibility: {},
      footprint_mm: { width_mm: 148, height_mm: 210 },
    })
    // "Edit from library" creates a draft; it must open at the saved size.
    const draftId = await store.createPlacementFromLibrary('lib-1', undefined, {
      asDraft: true,
    })
    const draft = store.placements.find((pl) => pl.id === draftId)!
    expect(draft.width_mm).toBeCloseTo(148, 3)
    expect(draft.height_mm).toBeCloseTo(210, 3)
    await nextTick()
    // The saved footprint survived (not overwritten by an auto-fit).
    expect(library.getFileSettings('lib-1')?.footprint_mm).toEqual({
      width_mm: 148,
      height_mm: 210,
    })
  })
})
