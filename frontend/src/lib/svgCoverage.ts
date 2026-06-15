// Per-colour area coverage of a preview SVG, measured by rasterising it to a
// small canvas and histogramming pixels onto the nearest segment centroid.
//
// Used to make the decoupled "number of colours" (M) reduction DOMINANCE-aware:
// the M-ink palette should keep the colours that cover the most AREA, not just
// the most perceptually-distinct ones. The raw /preview SVG paints each segment
// in its own centroid, so the rasterised histogram is the true per-segment area
// (anti-aliased edge pixels snap to their nearest centroid). Browser-only —
// returns an empty map where there's no canvas (SSR / happy-dom tests), so the
// caller falls back to an unweighted merge.
import { deltaE2000, rgbToLab } from './nearestColor'

// Raster size: big enough that small regions register, small enough that the
// per-pixel nearest-centroid snap stays well under a frame.
const RASTER = 96

/**
 * Measure each centroid's fractional area in ``svg``.
 *
 * @returns ``centroidHexLower → coverage`` (fractions summing to ~1 over the
 *   painted area). Empty when there's no canvas or the SVG fails to load.
 */
export async function colorCoverageFromSvg(
  svg: string,
  centroids: readonly string[],
): Promise<Map<string, number>> {
  const out = new Map<string, number>()
  if (
    !svg ||
    !centroids.length ||
    typeof document === 'undefined' ||
    typeof Image === 'undefined'
  ) {
    return out
  }

  let img: HTMLImageElement
  try {
    img = new Image()
    const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('svg image load failed'))
      img.src = url
    })
  } catch {
    return out
  }

  const canvas = document.createElement('canvas')
  canvas.width = RASTER
  canvas.height = RASTER
  const ctx = canvas.getContext('2d')
  if (!ctx) return out
  try {
    ctx.drawImage(img, 0, 0, RASTER, RASTER)
  } catch {
    return out
  }
  let data: Uint8ClampedArray
  try {
    data = ctx.getImageData(0, 0, RASTER, RASTER).data
  } catch {
    return out
  }

  const labs = centroids.map((h) => h.replace('#', '').toLowerCase())
  const centroidLab = centroids.map((h) => {
    const body = h.replace('#', '')
    return rgbToLab(
      parseInt(body.slice(0, 2), 16),
      parseInt(body.slice(2, 4), 16),
      parseInt(body.slice(4, 6), 16),
    )
  })
  const counts = new Array<number>(centroids.length).fill(0)
  let total = 0
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3]! < 128) continue // skip transparent (paper) pixels
    const lab = rgbToLab(data[i]!, data[i + 1]!, data[i + 2]!)
    let best = 0
    let bestD = Infinity
    for (let c = 0; c < centroidLab.length; c++) {
      const d = deltaE2000(lab, centroidLab[c]!)
      if (d < bestD) {
        bestD = d
        best = c
      }
    }
    counts[best]!++
    total++
  }
  if (total === 0) return out
  for (let c = 0; c < centroids.length; c++) {
    out.set(`#${labs[c]}`, counts[c]! / total)
  }
  return out
}
