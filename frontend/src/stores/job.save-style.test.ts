// @vitest-environment happy-dom
import { nextTick } from 'vue'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MachineProfile } from '../api/client'

// Verifies the "Enregistrer le style" (save style) path: in the editor it
// commits the draft by re-uploading (useEditorConfirmation → uploadSelected
// → store.upload). That re-convert must NOT resize the artwork — a file the
// operator sized to A6 has to stay A6 across the save, and the footprint
// memory has to keep pointing at A6 so the next drag-drop restores it.

const SVG_BEFORE =
  '<svg xmlns="http://www.w3.org/2000/svg" width="296" height="420" ' +
  'viewBox="0 0 296 420"><g><rect x="0" y="0" width="296" height="420"/></g></svg>'
// The re-render returns geometry that is intentionally identical regardless
// of page size (bitmap geometry is resolution-based, not page-based) — only
// the on-plan footprint changes between A4 and A6.
const SVG_AFTER = SVG_BEFORE

function detail(svg: string) {
  return {
    file_id: 'lib-1',
    source_file: 'photo.png',
    source_mime: 'image/png',
    rerenderable: true,
    svg,
    layers: [
      {
        layer_id: 'L1',
        source_color: '#000000',
        bbox: { x_min: 0, y_min: 0, x_max: 296, y_max: 420 },
      },
    ],
    upload_warnings: [],
    warnings: [],
    upload_metadata: {},
  }
}

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, getLibraryFile: (id: string) => getLibraryFile(id) }
})

const getLibraryFile = vi.fn()

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

describe('save style (re-convert) keeps the chosen page size', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    getLibraryFile.mockResolvedValue(detail(SVG_BEFORE))
    const job = useJobStore()
    const { profiles, selectedProfileName } = storeToRefs(job)
    profiles.value = [makeProfile()]
    selectedProfileName.value = 'Test A3'
  })

  it('preserves an A6 footprint across a save-style re-upload, and the next drop restores it', async () => {
    const store = useJobStore()
    const library = useLibraryStore()
    // Place the file and size it to A6 — the editor's format selector.
    const id = await store.createPlacementFromLibrary('lib-1')
    store.selectPlacement(id)
    store.setDrawing({ width_mm: 105, height_mm: 148 })
    await nextTick()
    expect(library.getFileSettings('lib-1')?.footprint_mm).toEqual({
      width_mm: 105,
      height_mm: 148,
    })

    // "Enregistrer le style" re-uploads the file through the library store;
    // stub that round-trip so the test drives the store logic only.
    library.upload = vi.fn().mockResolvedValue({ file: detail(SVG_AFTER), existing: true })
    await store.upload(new File(['x'], 'photo.png', { type: 'image/png' }), {
      target_width_mm: 105,
      target_height_mm: 148,
    })
    const after = store.placements.find((p) => p.id === id)!
    // The re-convert must keep the A6 size, not snap back to a fit size.
    expect(after.width_mm).toBeCloseTo(105, 3)
    expect(after.height_mm).toBeCloseTo(148, 3)

    // And a fresh drop still comes back at A6.
    const dropId = await store.createPlacementFromLibrary('lib-1')
    const dropped = store.placements.find((p) => p.id === dropId)!
    expect(dropped.width_mm).toBeCloseTo(105, 3)
    expect(dropped.height_mm).toBeCloseTo(148, 3)
  })
})
