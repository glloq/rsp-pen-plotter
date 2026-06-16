// @vitest-environment happy-dom
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { MachineProfile } from '../api/client'

// A raw SVG (Inkscape / Illustrator export) reports no page metadata, so
// the placement size has to come from the document's own physical
// width/height. The library detail is fetched through ``getLibraryFile``;
// each test overrides the resolved value to control the SVG under test.
const A4_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" ' +
  'viewBox="0 0 210 297"><rect x="0" y="0" width="210" height="297" ' +
  'fill="none" stroke="black"/></svg>'

// A unitless icon: no physical page, so it must keep the legacy
// fit-to-workspace behaviour (scaled up to fill the usable area).
const ICON_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" ' +
  'viewBox="0 0 24 24"><rect x="0" y="0" width="24" height="24" ' +
  'fill="none" stroke="black"/></svg>'

const getLibraryFile = vi.fn()

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, getLibraryFile: (id: string) => getLibraryFile(id) }
})

import { useJobStore } from './job'

function detailFor(
  svg: string,
  bbox: { x_max: number; y_max: number },
  upload_metadata: Record<string, unknown> = {},
) {
  return {
    file_id: 'lib-1',
    source_file: 'drawing.svg',
    source_mime: 'image/svg+xml',
    rerenderable: false,
    svg,
    layers: [
      {
        layer_id: 'L1',
        source_color: '#000000',
        bbox: { x_min: 0, y_min: 0, x_max: bbox.x_max, y_max: bbox.y_max },
      },
    ],
    upload_warnings: [],
    upload_metadata,
  }
}

function makeProfile(): MachineProfile {
  return {
    name: 'Test A3',
    units: 'mm',
    // A3 bed: comfortably larger than A4 so an A4 drawing lands un-clamped.
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

describe('library drop sizes a raw SVG to its physical page', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    seedProfile()
  })

  it('places an A4 SVG at 210 × 297 mm, not rescaled to the workspace', async () => {
    getLibraryFile.mockResolvedValue(detailFor(A4_SVG, { x_max: 210, y_max: 297 }))
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    const p = store.placements.find((pl) => pl.id === id)!
    // Margin defaults to 10 mm → usable 277 × 400 mm easily fits A4, so
    // the placement keeps its true page size instead of fitting the bed.
    expect(p.width_mm).toBeCloseTo(210, 3)
    expect(p.height_mm).toBeCloseTo(297, 3)
  })

  it('still fits a unitless icon to the workspace (no physical size)', async () => {
    getLibraryFile.mockResolvedValue(detailFor(ICON_SVG, { x_max: 24, y_max: 24 }))
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    const p = store.placements.find((pl) => pl.id === id)!
    // 24-unit bbox scaled to the 277 × 400 mm usable area, aspect-locked
    // on the limiting (width) axis → 277 mm.
    expect(p.width_mm).toBeCloseTo(277, 3)
    expect(p.height_mm).toBeCloseTo(277, 3)
  })

  it('sizes a bitmap (px viewBox) to the A5 page reported in metadata', async () => {
    // A processed image: the SVG viewBox is in raster pixels and carries no
    // physical unit, so the A5 footprint comes from upload_metadata (the
    // backend reports the operator's target_width/height_mm there). Without
    // it the image was rescaled to fill the bed — bigger than A5.
    const bitmapSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="296" height="420" ' +
      'viewBox="0 0 296 420"><rect x="0" y="0" width="296" height="420" ' +
      'fill="none" stroke="black"/></svg>'
    getLibraryFile.mockResolvedValue(
      detailFor(bitmapSvg, { x_max: 296, y_max: 420 }, { page_width_mm: 148, page_height_mm: 210 }),
    )
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    const p = store.placements.find((pl) => pl.id === id)!
    expect(p.width_mm).toBeCloseTo(148, 3)
    expect(p.height_mm).toBeCloseTo(210, 3)
  })
})
