// Geometry + derived rendering data for the SheetPreview (L10 #2).
//
// Owns the pure math + computed views the canvas + handles consume:
//
//   - ``workspace``: profile-derived sheet bounds + pad
//   - ``grid``: the minor / major / cm-label grid lines
//   - ``previewSheetRect``: the decorative format overlay from
//     LayoutSection
//   - ``renderedPlacements``: per-placement absolute footprint,
//     out-of-bounds flag, sanitized SVG content + preview URL,
//     plus the tier-selection helpers
//   - ``snap`` / ``pxPerMm`` / ``clientToSvgMm``: coordinate helpers
//     for the gesture layer
//
// Inputs are passed as refs so the composable stays decoupled from
// the specific store + DOM tree. The orchestrator wires the live
// ``useJobStore`` placement list + ``useUiStore`` preview sheet in;
// future callers (tests, a standalone preview) can pass any reactive
// source.

import { computed, reactive, type Ref } from 'vue'
import DOMPurify from 'dompurify'
import { libraryFileOriginalUrl } from '../api/client'
import type { MachineProfile } from '../api/client'
import type { Placement } from '../stores/job'
import { applyPhysicalStrokeWidth, mmPerViewBoxUnit } from '../lib/penWidth'
import type { PlanPreviewMode } from '../stores/ui'

// In 'auto' mode a placement keeps its (cheap) raster preview once its
// chosen-style SVG carries more than this many pen primitives — past
// roughly this point an inline SVG inside a foreignObject starts to make
// pan/zoom stutter on modest hardware (the appliance Pi), so we trade
// the WYSIWYG vector for the flat bitmap. Tuned conservatively: simple
// line/halftone styles stay well under it; only dense multi-pass hatching
// trips the fallback.
export const AUTO_SVG_PRIMITIVE_LIMIT = 5000

export interface PreviewSheet {
  width_mm: number
  height_mm: number
  x_mm?: number
  y_mm?: number
}

export interface RenderedPlacement {
  placement: Placement
  footprint: { x_min: number; y_min: number; x_max: number; y_max: number }
  exceeds: boolean
  cleanSvg: string
  /** Number of pen primitives (path / line / circle / polyline /
   *  polygon) in ``cleanSvg``. Drives the 'auto' plan-preview heuristic
   *  — a dense SVG keeps the cheap raster preview to protect pan/zoom
   *  smoothness. 0 when there's no SVG yet. */
  svgPrimitiveCount: number
  /** URL to the original uploaded bytes, only when the file is an
   *  image we can display directly in the browser (raster + SVG
   *  sources). Empty for PDFs / typography / other formats — those
   *  fall back to the plotter SVG (tier 2) immediately. */
  previewUrl: string
}

export interface SheetWorkspace {
  profile: MachineProfile
  ws: MachineProfile['workspace']
  wsW: number
  wsH: number
  pad: number
}

export interface SheetGrid {
  xs: number[]
  ys: number[]
  majorXs: number[]
  majorYs: number[]
  labelsX: { x: number; cm: number }[]
  labelsY: { y: number; cm: number }[]
}

export interface SheetGeometryInputs {
  profile: Ref<MachineProfile | null>
  placements: Ref<readonly Placement[]>
  previewSheet: Ref<PreviewSheet | null>
  /** Plan-tab rendering preference (image / svg / auto). Optional so
   *  callers that don't care (tests, future surfaces) default to the
   *  adaptive 'auto' behaviour. */
  planPreviewMode?: Ref<PlanPreviewMode>
  snapMm: Ref<number>
  /** The container ``<div>`` whose clientWidth drives ``pxPerMm``. */
  container: Ref<HTMLElement | null>
  /** The SVG element whose ``getScreenCTM()`` converts client coords
   *  into workspace mm. */
  svgEl: Ref<SVGSVGElement | null>
  /** Canonical-hex → pen tip width (mm) from the available-colours
   *  inventory. When provided, each coloured group in a placement's SVG
   *  is re-stroked to its assigned pen's physical width at display time.
   *  Optional so standalone callers / tests can omit it. */
  strokeWidthMm?: Ref<Map<string, number>>
}

// Count the pen-stroke primitives in an SVG string. Mirrors the
// diagnostics counter in EditPreviewPane: each <path>/<line>/<circle>/
// <polyline>/<polygon> is roughly one stroke, and the sum is a good
// proxy for how expensive the SVG is to paint.
export function countSvgPrimitives(svg: string): number {
  if (!svg) return 0
  // The trailing ``[\s/>]`` class matches the delimiter after the tag
  // name — a space (``<path d=``), a self-close (``<line/>``) or a plain
  // close (``<circle>``) — so ``<pathological>`` never counts as a path.
  return (
    (svg.match(/<path[\s/>]/g)?.length ?? 0) +
    (svg.match(/<line[\s/>]/g)?.length ?? 0) +
    (svg.match(/<circle[\s/>]/g)?.length ?? 0) +
    (svg.match(/<polyline[\s/>]/g)?.length ?? 0) +
    (svg.match(/<polygon[\s/>]/g)?.length ?? 0)
  )
}

function isDisplayableMime(mime: string): boolean {
  // Anything the browser can paint into an SVG ``<image>`` without a
  // server-side render step. SVG counts here because we draw it
  // through the bytes endpoint, which serves it with the right
  // content type.
  if (!mime) return false
  return mime.startsWith('image/')
}

export function useSheetGeometry(inputs: SheetGeometryInputs) {
  // DOMPurify.sanitize is expensive on large SVGs; without
  // memoization it runs for every placement on every pointer-move
  // during drag, which chokes the tab. Cache by placement id + raw
  // svg so unchanged SVGs are reused across recomputations. Entries
  // are evicted for placements that disappear from the plan.
  const sanitizedCache = new Map<string, { svg: string; clean: string; count: number }>()

  // Per-library-file load status for the source-preview image.
  // ``reactive`` so onload / onerror on the SVG ``<image>`` re-trigger
  // the template without recomputing the heavy
  // ``renderedPlacements`` chain.
  type PreviewStatus = 'loading' | 'loaded' | 'failed'
  const previewStatus = reactive<Record<string, PreviewStatus>>({})

  function onPreviewLoad(fileId: string): void {
    previewStatus[fileId] = 'loaded'
  }
  function onPreviewError(fileId: string): void {
    previewStatus[fileId] = 'failed'
  }

  const workspace = computed<SheetWorkspace | null>(() => {
    const profile = inputs.profile.value
    if (!profile) return null
    const ws = profile.workspace
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    if (wsW <= 0 || wsH <= 0) return null
    const pad = Math.max(wsW, wsH) * 0.04
    return { profile, ws, wsW, wsH, pad }
  })

  // Stroke-width restyle cache: keyed by raw svg + scale + inventory
  // signature so resizing a placement (new scale) or editing a pen
  // width (new signature) recomputes, but an unchanged frame reuses the
  // parsed result instead of re-running DOMParser on every pointer-move.
  const styledCache = new Map<string, { key: string; out: string }>()

  const renderedPlacements = computed<RenderedPlacement[]>(() => {
    const w = workspace.value
    if (!w) return []
    const widthMap = inputs.strokeWidthMm?.value ?? null
    // Compact signature of the inventory widths so the styled cache busts
    // when the operator changes a pen tip width.
    const mapSig = widthMap ? [...widthMap.entries()].map(([h, mm]) => `${h}:${mm}`).join(',') : ''
    const seen = new Set<string>()
    const out = inputs.placements.value.map((p) => {
      seen.add(p.id)
      const x_min = w.ws.x_min + p.x_mm
      const y_min = w.ws.y_min + p.y_mm
      const x_max = x_min + p.width_mm
      const y_max = y_min + p.height_mm
      const exceeds =
        x_min < w.ws.x_min - 0.01 ||
        y_min < w.ws.y_min - 0.01 ||
        x_max > w.ws.x_max + 0.01 ||
        y_max > w.ws.y_max + 0.01
      let cleanSvg = ''
      let svgPrimitiveCount = 0
      if (p.svg) {
        const cached = sanitizedCache.get(p.id)
        if (cached && cached.svg === p.svg) {
          cleanSvg = cached.clean
          svgPrimitiveCount = cached.count
        } else {
          cleanSvg = DOMPurify.sanitize(p.svg, {
            USE_PROFILES: { svg: true, svgFilters: true },
          })
          // Count once at sanitize time and cache alongside the clean
          // SVG — the 'auto' heuristic reads it on every pointer-move
          // during drag, so it must not re-scan the string each frame.
          svgPrimitiveCount = countSvgPrimitives(cleanSvg)
          sanitizedCache.set(p.id, { svg: p.svg, clean: cleanSvg, count: svgPrimitiveCount })
        }
        // Re-stroke each coloured group at its assigned pen's physical
        // width. Applied to the sanitised SVG (post-DOMPurify) so the
        // operator sees a true-to-life line thickness in the preview.
        if (widthMap && widthMap.size) {
          const mmPerUnit = mmPerViewBoxUnit(cleanSvg, p.width_mm, p.height_mm)
          if (mmPerUnit) {
            const key = `${mmPerUnit.toFixed(4)}|${mapSig}`
            const cached = styledCache.get(p.id)
            if (cached && cached.key === key) {
              cleanSvg = cached.out
            } else {
              cleanSvg = applyPhysicalStrokeWidth(cleanSvg, widthMap, mmPerUnit)
              styledCache.set(p.id, { key, out: cleanSvg })
            }
          }
        }
      } else {
        sanitizedCache.delete(p.id)
        styledCache.delete(p.id)
      }
      // Tier 1 source preview is only attempted when (a) we have a
      // library entry to read bytes from, and (b) the MIME is one
      // the browser can paint without an extra server-side render
      // step.
      const previewUrl =
        p.library_file_id && isDisplayableMime(p.source_mime)
          ? libraryFileOriginalUrl(p.library_file_id)
          : ''
      return {
        placement: p,
        footprint: { x_min, y_min, x_max, y_max },
        exceeds,
        cleanSvg,
        svgPrimitiveCount,
        previewUrl,
      }
    })
    for (const id of sanitizedCache.keys()) {
      if (!seen.has(id)) sanitizedCache.delete(id)
    }
    for (const id of styledCache.keys()) {
      if (!seen.has(id)) styledCache.delete(id)
    }
    return out
  })

  /** Should the chosen-style plotter SVG win over the raster source for
   *  this placement? Only meaningful when both are actually available;
   *  callers still guard on ``cleanSvg`` / ``previewUrl`` presence. */
  function prefersStyleSvg(rp: RenderedPlacement): boolean {
    if (!rp.cleanSvg) return false
    const mode = inputs.planPreviewMode?.value ?? 'auto'
    if (mode === 'image') return false
    if (mode === 'svg') return true
    // 'auto': WYSIWYG vector unless it's dense enough to risk laggy
    // pan/zoom, in which case keep the cheap raster.
    return rp.svgPrimitiveCount <= AUTO_SVG_PRIMITIVE_LIMIT
  }

  /** Should tier 1 (source preview ``<image>``) actually be shown? */
  function showsPreviewImage(rp: RenderedPlacement): boolean {
    if (!rp.previewUrl) return false
    const status = previewStatus[rp.placement.library_file_id ?? '']
    if (status === 'failed') return false
    // The operator (or the auto heuristic) asked for the style SVG and
    // we have one — don't paint the raster underneath it.
    if (prefersStyleSvg(rp)) return false
    return true
  }

  /** Should tier 2 (inline plotter SVG) be shown? When the raster is the
   *  preferred layer we still paint the SVG until the image finishes
   *  loading (so the footprint isn't blank), then hide it to avoid
   *  double-painting. When the SVG is preferred it's shown outright. */
  function showsPlotterSvg(rp: RenderedPlacement): boolean {
    if (!rp.cleanSvg) return false
    if (!rp.previewUrl) return true
    if (prefersStyleSvg(rp)) return true
    const status = previewStatus[rp.placement.library_file_id ?? '']
    return status !== 'loaded'
  }

  /** Tier 3: nothing else worked — render a small MIME badge so the
   *  placement footprint isn't visually empty. */
  function showsMimeBadge(rp: RenderedPlacement): boolean {
    if (rp.cleanSvg) return false
    if (showsPreviewImage(rp)) return false
    return true
  }

  const anyExceeds = computed(() => renderedPlacements.value.some((r) => r.exceeds))

  // Sheet overlay shown when the user picked a sheet format in
  // LayoutSection. Anchored at the workspace top-left, clipped to
  // the workspace bounds, and purely decorative — no impact on
  // placement logic.
  const previewSheetRect = computed(() => {
    const w = workspace.value
    const sheet = inputs.previewSheet.value
    if (!w || !sheet) return null
    const offX = Math.max(0, Math.min(sheet.x_mm ?? 0, w.wsW))
    const offY = Math.max(0, Math.min(sheet.y_mm ?? 0, w.wsH))
    // Clip the overlay to the remaining workspace so an offset sheet that
    // would overflow stays inside the drawn bed.
    const width = Math.max(0, Math.min(sheet.width_mm, w.wsW - offX))
    const height = Math.max(0, Math.min(sheet.height_mm, w.wsH - offY))
    if (width <= 0 || height <= 0) return null
    return { x: w.ws.x_min + offX, y: w.ws.y_min + offY, width, height }
  })

  // Grid: minor lines every 10 mm (1 cm), major every 50 mm (5 cm).
  const grid = computed<SheetGrid | null>(() => {
    const w = workspace.value
    if (!w) return null
    const xs: number[] = []
    const ys: number[] = []
    const majorXs: number[] = []
    const majorYs: number[] = []
    const labelsX: { x: number; cm: number }[] = []
    const labelsY: { y: number; cm: number }[] = []
    for (let x = Math.ceil(w.ws.x_min / 10) * 10; x <= w.ws.x_max + 0.0001; x += 10) {
      xs.push(x)
      if (Math.round(x) % 50 === 0) {
        majorXs.push(x)
        labelsX.push({ x, cm: Math.round(x / 10) })
      }
    }
    for (let y = Math.ceil(w.ws.y_min / 10) * 10; y <= w.ws.y_max + 0.0001; y += 10) {
      ys.push(y)
      if (Math.round(y) % 50 === 0) {
        majorYs.push(y)
        labelsY.push({ y, cm: Math.round(y / 10) })
      }
    }
    return { xs, ys, majorXs, majorYs, labelsX, labelsY }
  })

  function snap(value: number): number {
    if (inputs.snapMm.value <= 0) return value
    return Math.round(value / inputs.snapMm.value) * inputs.snapMm.value
  }

  function pxPerMm(): number {
    const w = workspace.value
    if (!w || !inputs.container.value) return 1
    return inputs.container.value.clientWidth / (w.wsW + 2 * w.pad)
  }

  function clientToSvgMm(clientX: number, clientY: number): { x: number; y: number } | null {
    const svg = inputs.svgEl.value
    if (!svg) return null
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const ctm = svg.getScreenCTM()
    if (!ctm) return null
    const local = pt.matrixTransform(ctm.inverse())
    return { x: local.x, y: local.y }
  }

  return {
    workspace,
    renderedPlacements,
    grid,
    previewSheetRect,
    anyExceeds,
    snap,
    pxPerMm,
    clientToSvgMm,
    showsPreviewImage,
    showsPlotterSvg,
    showsMimeBadge,
    onPreviewLoad,
    onPreviewError,
  }
}
