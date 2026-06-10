// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useSheetGeometry, countSvgPrimitives, AUTO_SVG_PRIMITIVE_LIMIT } from './useSheetGeometry'
import type { MachineProfile } from '../api/client'
import type { Placement } from '../stores/job'
import type { PlanPreviewMode } from '../stores/ui'

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
    ...overrides,
  } as Placement
}

function makeInputs(opts: {
  profile?: MachineProfile | null
  placements?: Placement[]
  previewSheet?: { width_mm: number; height_mm: number } | null
  planPreviewMode?: PlanPreviewMode
  snapMm?: number
}) {
  return {
    profile: ref<MachineProfile | null>(opts.profile ?? null),
    placements: ref<readonly Placement[]>(opts.placements ?? []),
    previewSheet: ref<{ width_mm: number; height_mm: number } | null>(opts.previewSheet ?? null),
    planPreviewMode: ref<PlanPreviewMode>(opts.planPreviewMode ?? 'auto'),
    snapMm: ref<number>(opts.snapMm ?? 0),
    container: ref<HTMLElement | null>(null),
    svgEl: ref<SVGSVGElement | null>(null),
  }
}

// A well-formed SVG (xmlns + viewBox) survives DOMPurify under happy-dom
// — unlike the bare ``<svg>`` snippets elsewhere in this file, which come
// back empty. ``paths`` controls the primitive count the 'auto'
// heuristic reads.
function makeSvg(paths: number): string {
  const body = Array.from({ length: paths }, (_, i) => `<path d="M${i} 0 L${i} 1"/>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">${body}</svg>`
}

// A raster placement that ALSO carries a chosen-style SVG: both the
// tier-1 image and the tier-2 plotter SVG are available, so the mode
// decides which one wins.
function makeRasterWithSvg(paths: number): Placement {
  return makePlacement({
    id: 'raster',
    library_file_id: 'lib-png',
    source_mime: 'image/png',
    svg: makeSvg(paths),
  })
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

describe('useSheetGeometry stroke-width restyle cache', () => {
  function makeStrokedSvg(paths: number): string {
    const body = Array.from(
      { length: paths },
      (_, i) => `<path stroke="#ff0000" d="M${i} 0 L${i} 1"/>`,
    ).join('')
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">${body}</svg>`
  }

  it('recomputes the styled SVG when /rerender swaps the SVG at the same size + inventory', () => {
    // Regression: the styled cache used to be keyed only by
    // mmPerUnit|inventory-signature, so a /rerender that replaced
    // placement.svg without changing size or pen widths kept serving the
    // stale styled output — the canvas showed the pre-rerender drawing
    // whenever stroke widths existed.
    const placements = ref<readonly Placement[]>([
      makePlacement({ id: 'p1', svg: makeStrokedSvg(2) }),
    ])
    const inputs = {
      ...makeInputs({ profile: makeProfile() }),
      placements,
      strokeWidthMm: ref(new Map([['#ff0000', 0.5]])),
    }
    const g = useSheetGeometry(inputs)
    const before = g.renderedPlacements.value[0]!.cleanSvg
    expect((before.match(/<path/g) ?? []).length).toBe(2)

    // Same id, same size, same inventory — only the SVG content changes.
    placements.value = [makePlacement({ id: 'p1', svg: makeStrokedSvg(5) })]
    const after = g.renderedPlacements.value[0]!.cleanSvg
    expect((after.match(/<path/g) ?? []).length).toBe(5)
    expect(after).not.toBe(before)
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

describe('countSvgPrimitives', () => {
  it('counts each stroke-bearing element', () => {
    const svg = '<svg><path d="M0 0"/><line/><circle/><polyline/><polygon/><rect/><g></g></svg>'
    // path + line + circle + polyline + polygon = 5; rect / g don't count.
    expect(countSvgPrimitives(svg)).toBe(5)
  })

  it('returns 0 for an empty string', () => {
    expect(countSvgPrimitives('')).toBe(0)
  })

  it('does not over-count substrings (e.g. <pathological>)', () => {
    // The trailing delimiter in the regex stops <pathological> matching
    // the <path counter.
    expect(countSvgPrimitives('<pathological/>')).toBe(0)
  })
})

describe('useSheetGeometry plan-preview tier selection', () => {
  it("mode 'image' paints the raster even when a style SVG exists", () => {
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        placements: [makeRasterWithSvg(3)],
        planPreviewMode: 'image',
      }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(g.showsPreviewImage(rp)).toBe(true)
    // Mutually exclusive with the SVG tier — the canvas must never
    // double-paint, otherwise the chosen-style SVG flashes through
    // under the raster until the <img> finishes decoding.
    expect(g.showsPlotterSvg(rp)).toBe(false)
    expect(g.showsMimeBadge(rp)).toBe(false)
  })

  it("mode 'svg' paints the style SVG and hides the raster", () => {
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        placements: [makeRasterWithSvg(3)],
        planPreviewMode: 'svg',
      }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(g.showsPreviewImage(rp)).toBe(false)
    expect(g.showsPlotterSvg(rp)).toBe(true)
  })

  it("mode 'svg' still falls back to the raster before conversion (no SVG yet)", () => {
    const noSvg = makePlacement({
      id: 'raster',
      library_file_id: 'lib-png',
      source_mime: 'image/png',
      svg: '',
    })
    const g = useSheetGeometry(
      makeInputs({ profile: makeProfile(), placements: [noSvg], planPreviewMode: 'svg' }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(g.showsPreviewImage(rp)).toBe(true)
    expect(g.showsPlotterSvg(rp)).toBe(false)
  })

  it("mode 'auto' prefers the style SVG for light drawings", () => {
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        placements: [makeRasterWithSvg(10)],
        planPreviewMode: 'auto',
      }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(rp.svgPrimitiveCount).toBe(10)
    expect(g.showsPreviewImage(rp)).toBe(false)
    expect(g.showsPlotterSvg(rp)).toBe(true)
  })

  it("mode 'auto' keeps the raster for heavy drawings past the limit", () => {
    const heavy = AUTO_SVG_PRIMITIVE_LIMIT + 1
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        placements: [makeRasterWithSvg(heavy)],
        planPreviewMode: 'auto',
      }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(rp.svgPrimitiveCount).toBe(heavy)
    expect(g.showsPreviewImage(rp)).toBe(true)
    // Heavy SVG must NOT also be painted under the raster — the layered
    // render is exactly the flicker that the tier selector exists to
    // prevent.
    expect(g.showsPlotterSvg(rp)).toBe(false)
  })

  it('keeps the three tier predicates mutually exclusive across every mode', () => {
    // Walk every combination of (mode, hasSvg, hasRaster) and assert
    // that exactly one of showsPreviewImage / showsPlotterSvg /
    // showsMimeBadge ever fires per placement. The plan canvas relies on
    // this invariant to avoid layering two tiers on top of each other.
    const modes: PlanPreviewMode[] = ['auto', 'image', 'svg']
    const placements = [
      makeRasterWithSvg(3), // raster + svg
      makePlacement({ id: 'rasterOnly', library_file_id: 'r', source_mime: 'image/png', svg: '' }),
      makePlacement({ id: 'svgOnly', library_file_id: null, svg: makeSvg(4) }),
      makePlacement({
        id: 'nothing',
        library_file_id: 'pdf',
        source_mime: 'application/pdf',
        svg: '',
      }),
    ]
    for (const mode of modes) {
      const g = useSheetGeometry(
        makeInputs({ profile: makeProfile(), placements, planPreviewMode: mode }),
      )
      for (const rp of g.renderedPlacements.value) {
        const picks = [g.showsPreviewImage(rp), g.showsPlotterSvg(rp), g.showsMimeBadge(rp)].filter(
          Boolean,
        ).length
        expect(picks).toBe(1)
      }
    }
  })

  it('always shows the SVG when there is no displayable raster (mode image)', () => {
    // A vector/typography source with no library image: even in 'image'
    // mode the plotter SVG is the only thing to paint.
    const g = useSheetGeometry(
      makeInputs({
        profile: makeProfile(),
        placements: [makePlacement({ library_file_id: null, svg: makeSvg(4) })],
        planPreviewMode: 'image',
      }),
    )
    const rp = g.renderedPlacements.value[0]!
    expect(g.showsPreviewImage(rp)).toBe(false)
    expect(g.showsPlotterSvg(rp)).toBe(true)
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
