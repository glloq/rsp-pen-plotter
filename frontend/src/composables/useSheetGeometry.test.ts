// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useSheetGeometry } from './useSheetGeometry'
import type { MachineProfile } from '../api/client'
import type { Placement } from '../stores/job'

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
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function makePlacement(overrides: Partial<Placement> = {}): Placement {
  return {
    id: 'p1',
    source_file: 'file1',
    library_file_id: null,
    source_mime: 'image/svg+xml',
    upload_metadata: {},
    x_mm: 10,
    y_mm: 20,
    width_mm: 100,
    height_mm: 80,
    rotation: 0,
    flip_h: false,
    flip_v: false,
    svg: null,
    layers: [],
    variants: [],
    active_variant_id: null,
    ...overrides,
  } as Placement
}

function makeInputs(opts: {
  profile?: MachineProfile | null
  placements?: Placement[]
  previewSheet?: { width_mm: number; height_mm: number } | null
  snapMm?: number
}) {
  return {
    profile: ref<MachineProfile | null>(opts.profile ?? null),
    placements: ref<readonly Placement[]>(opts.placements ?? []),
    previewSheet: ref<{ width_mm: number; height_mm: number } | null>(opts.previewSheet ?? null),
    snapMm: ref<number>(opts.snapMm ?? 0),
    container: ref<HTMLElement | null>(null),
    svgEl: ref<SVGSVGElement | null>(null),
  }
}

describe('useSheetGeometry workspace', () => {
  it('returns null when no profile is supplied', () => {
    const g = useSheetGeometry(makeInputs({ profile: null }))
    expect(g.workspace.value).toBeNull()
  })

  it('derives wsW / wsH / pad from the profile workspace', () => {
    // The pad is 4% of the longer side so the workspace outline has
    // room to breathe inside the SVG viewBox — operators noted the
    // outline was clipped on tight viewports without it.
    const g = useSheetGeometry(makeInputs({ profile: makeProfile() }))
    const w = g.workspace.value
    expect(w).not.toBeNull()
    expect(w!.wsW).toBe(297)
    expect(w!.wsH).toBe(420)
    expect(w!.pad).toBeCloseTo(420 * 0.04)
  })

  it('returns null when the workspace bounds are degenerate', () => {
    const profile = makeProfile()
    profile.workspace = { x_min: 0, y_min: 0, x_max: 0, y_max: 0 }
    const g = useSheetGeometry(makeInputs({ profile }))
    expect(g.workspace.value).toBeNull()
  })
})

describe('useSheetGeometry renderedPlacements', () => {
  it('projects placement coordinates to absolute machine coords', () => {
    const placement = makePlacement({ x_mm: 10, y_mm: 20, width_mm: 50, height_mm: 30 })
    const g = useSheetGeometry(makeInputs({ profile: makeProfile(), placements: [placement] }))
    const rp = g.renderedPlacements.value[0]
    expect(rp).toBeDefined()
    // Workspace origin is (0, 0) so footprint = (x_mm, y_mm, x_mm+w, y_mm+h).
    expect(rp!.footprint).toEqual({ x_min: 10, y_min: 20, x_max: 60, y_max: 50 })
    expect(rp!.exceeds).toBe(false)
  })

  it('flags placements whose footprint exceeds the workspace bounds', () => {
    // Bigger than 297mm wide → exceeds the A3 portrait workspace and
    // the canvas paints the bounding rect in red.
    const placement = makePlacement({ x_mm: 0, y_mm: 0, width_mm: 400, height_mm: 80 })
    const g = useSheetGeometry(makeInputs({ profile: makeProfile(), placements: [placement] }))
    expect(g.renderedPlacements.value[0]!.exceeds).toBe(true)
    expect(g.anyExceeds.value).toBe(true)
  })

  it('exposes a previewUrl only for displayable MIME types with a library id', () => {
    const png = makePlacement({
      id: 'png',
      library_file_id: 'lib-png',
      source_mime: 'image/png',
    })
    const pdf = makePlacement({
      id: 'pdf',
      library_file_id: 'lib-pdf',
      source_mime: 'application/pdf',
    })
    const nolib = makePlacement({
      id: 'noLib',
      library_file_id: null,
      source_mime: 'image/png',
    })
    const g = useSheetGeometry(
      makeInputs({ profile: makeProfile(), placements: [png, pdf, nolib] }),
    )
    const rps = g.renderedPlacements.value
    expect(rps[0]!.previewUrl).toContain('lib-png')
    expect(rps[1]!.previewUrl).toBe('')
    expect(rps[2]!.previewUrl).toBe('')
  })

  it('strips script tags from raw SVG via DOMPurify', () => {
    // The placement's ``svg`` field rides through ``v-html`` later,
    // so the sanitiser must scrub anything that would execute. We
    // assert on the negative side because DOMPurify under happy-dom
    // doesn't preserve every benign tag the way a real browser
    // would (the cleanSvg comes back empty for our tiny snippet) —
    // the security guarantee is what we care about here.
    const placement = makePlacement({
      svg: '<svg><script>alert(1)</script><circle cx="5" cy="5" r="3" /></svg>',
    })
    const g = useSheetGeometry(makeInputs({ profile: makeProfile(), placements: [placement] }))
    const rp = g.renderedPlacements.value[0]!
    expect(rp.cleanSvg).not.toContain('<script>')
    expect(rp.cleanSvg).not.toContain('alert')
  })
})

describe('useSheetGeometry grid', () => {
  it('emits cm labels at every 50mm step', () => {
    const g = useSheetGeometry(makeInputs({ profile: makeProfile() }))
    const grid = g.grid.value
    expect(grid).not.toBeNull()
    // A3 portrait: x in [0, 297] → cm labels at 0, 5, 10, 15, 20, 25 cm.
    const cmX = grid!.labelsX.map((l) => l.cm)
    expect(cmX).toEqual([0, 5, 10, 15, 20, 25])
    // y in [0, 420] → cm labels at 0..42 in steps of 5.
    const cmY = grid!.labelsY.map((l) => l.cm)
    expect(cmY).toEqual([0, 5, 10, 15, 20, 25, 30, 35, 40])
  })

  it('emits minor grid lines every 10mm', () => {
    const g = useSheetGeometry(makeInputs({ profile: makeProfile() }))
    // Workspace 0..297 → 30 minor X lines (0, 10, 20, ..., 290).
    expect(g.grid.value!.xs.length).toBe(30)
  })
})

describe('useSheetGeometry previewSheetRect', () => {
  it('returns null when no preview sheet is set', () => {
    const g = useSheetGeometry(makeInputs({ profile: makeProfile(), previewSheet: null }))
    expect(g.previewSheetRect.value).toBeNull()
  })

  it('clips the overlay to the workspace bounds when the sheet is larger', () => {
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        previewSheet: { width_mm: 500, height_mm: 500 },
      }),
    )
    const rect = g.previewSheetRect.value
    expect(rect).not.toBeNull()
    // Workspace is 297×420; the sheet rect is clipped to those bounds.
    expect(rect!.width).toBe(297)
    expect(rect!.height).toBe(420)
    expect(rect!.x).toBe(0)
    expect(rect!.y).toBe(0)
  })
})

describe('useSheetGeometry.snap', () => {
  it('returns the input unchanged when snapMm is 0', () => {
    const inputs = makeInputs({ profile: makeProfile(), snapMm: 0 })
    const g = useSheetGeometry(inputs)
    expect(g.snap(12.7)).toBe(12.7)
  })

  it('quantises to the snap step when snapMm > 0', () => {
    const inputs = makeInputs({ profile: makeProfile(), snapMm: 5 })
    const g = useSheetGeometry(inputs)
    expect(g.snap(12.4)).toBe(10)
    expect(g.snap(12.6)).toBe(15)
    expect(g.snap(15)).toBe(15)
  })
})
