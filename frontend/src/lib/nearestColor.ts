// Frontend mirror of ``backend/application/color_assignment.py``'s
// ``nearest_pool_hex`` — pure-numeric Lab + ΔE 2000 nearest-match.
//
// Used by the LayerCard's "↻ reset to auto" affordance so resetting an
// override happens instantly in the UI (no /rerender round-trip),
// matching what the backend would compute at the next /upload.

import { canonicalHex } from './penWidth'

function hexToRgb(hex: string): [number, number, number] {
  const body = hex.replace(/^#/, '').toLowerCase()
  const expanded =
    body.length === 3
      ? body
          .split('')
          .map((c) => c + c)
          .join('')
      : body
  return [
    parseInt(expanded.slice(0, 2), 16),
    parseInt(expanded.slice(2, 4), 16),
    parseInt(expanded.slice(4, 6), 16),
  ]
}

function gamma(x: number): number {
  return x > 0.04045 ? ((x + 0.055) / 1.055) ** 2.4 : x / 12.92
}

function srgbToXyz(rgb: [number, number, number]): [number, number, number] {
  // IEC 61966-2-1 piecewise gamma, then D65 matrix.
  const lin: [number, number, number] = [
    gamma(rgb[0] / 255),
    gamma(rgb[1] / 255),
    gamma(rgb[2] / 255),
  ]
  const [r, g, b] = lin
  return [
    0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
    0.2126729 * r + 0.7151522 * g + 0.072175 * b,
    0.0193339 * r + 0.119192 * g + 0.9503041 * b,
  ]
}

function xyzToLab(xyz: [number, number, number]): [number, number, number] {
  const refX = 0.95047
  const refY = 1.0
  const refZ = 1.08883
  const delta = 6 / 29
  const f = (t: number): number =>
    t > delta ** 3 ? Math.cbrt(t) : t / (3 * delta * delta) + 4 / 29
  const fx = f(xyz[0] / refX)
  const fy = f(xyz[1] / refY)
  const fz = f(xyz[2] / refZ)
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]
}

function hexToLab(hex: string): [number, number, number] {
  return xyzToLab(srgbToXyz(hexToRgb(hex)))
}

/** RGB (0-255 each) → CIE Lab. Exposed for pixel-histogram callers. */
export function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  return xyzToLab(srgbToXyz([r, g, b]))
}

export function deltaE2000(lab1: [number, number, number], lab2: [number, number, number]): number {
  // Faithful to the CIEDE2000 reference paper. Kept readable rather
  // than golfed; this is a one-shot per reset click so the cost is
  // a rounding error.
  const [L1, a1, b1] = lab1
  const [L2, a2, b2] = lab2
  const C1 = Math.hypot(a1, b1)
  const C2 = Math.hypot(a2, b2)
  const Cbar = (C1 + C2) / 2
  const g = 0.5 * (1 - Math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)))
  const a1p = (1 + g) * a1
  const a2p = (1 + g) * a2
  const C1p = Math.hypot(a1p, b1)
  const C2p = Math.hypot(a2p, b2)
  const h1p = (Math.atan2(b1, a1p) * 180) / Math.PI
  const h2p = (Math.atan2(b2, a2p) * 180) / Math.PI
  const h1pPos = (h1p + 360) % 360
  const h2pPos = (h2p + 360) % 360
  const dLp = L2 - L1
  const dCp = C2p - C1p
  let dhp = h2pPos - h1pPos
  if (dhp > 180) dhp -= 360
  if (dhp < -180) dhp += 360
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * Math.PI) / 360)
  const Lbar = (L1 + L2) / 2
  const Cbarp = (C1p + C2p) / 2
  let hbar = (h1pPos + h2pPos) / 2
  if (Math.abs(h1pPos - h2pPos) > 180) hbar += 180
  hbar %= 360
  const T =
    1 -
    0.17 * Math.cos(((hbar - 30) * Math.PI) / 180) +
    0.24 * Math.cos((2 * hbar * Math.PI) / 180) +
    0.32 * Math.cos(((3 * hbar + 6) * Math.PI) / 180) -
    0.2 * Math.cos(((4 * hbar - 63) * Math.PI) / 180)
  const sL = 1 + (0.015 * (Lbar - 50) ** 2) / Math.sqrt(20 + (Lbar - 50) ** 2)
  const sC = 1 + 0.045 * Cbarp
  const sH = 1 + 0.015 * Cbarp * T
  const rT =
    -2 *
    Math.sqrt(Cbarp ** 7 / (Cbarp ** 7 + 25 ** 7)) *
    Math.sin((60 * Math.exp(-(((hbar - 275) / 25) ** 2)) * Math.PI) / 180)
  return Math.sqrt(
    (dLp / sL) ** 2 + (dCp / sC) ** 2 + (dHp / sH) ** 2 + rT * (dCp / sC) * (dHp / sH),
  )
}

/**
 * Resolve the perceptually-nearest hex in ``pool`` to ``sourceHex``.
 *
 * @returns The canonical ``#rrggbb`` form of the winning candidate,
 *   or ``null`` when the pool is empty.
 */
export function nearestPoolHex(sourceHex: string, pool: readonly string[]): string | null {
  if (!pool.length) return null
  const sourceLab = hexToLab(sourceHex)
  let bestIdx = 0
  let bestD = Infinity
  for (let i = 0; i < pool.length; i++) {
    const d = deltaE2000(sourceLab, hexToLab(pool[i]!))
    if (d < bestD) {
      bestD = d
      bestIdx = i
    }
  }
  // Shared canonicaliser (lib/penWidth): lowercase #rrggbb, #rgb expanded.
  return canonicalHex(pool[bestIdx]!)
}

/**
 * Choose up to ``m`` available inks that best represent ``centroids`` — the
 * decoupled "number of colours" palette.
 *
 * Each segment centroid is first snapped to its nearest available ink (CIE Lab
 * ΔE 2000), then the inks are ranked by the total AREA of the segments that
 * landed on them and the top ``m`` are kept. The caller folds the remaining
 * segments onto the nearest survivor. Working in INK space (not centroid space)
 * means the palette is always real available colours — a grey region resolves
 * to the grey ink and stays put as the segment count (N) changes — and ranking
 * by area keeps the DOMINANT colours: the biggest regions survive a reduction
 * while specks fold in, instead of the 2nd-largest colour being merged away
 * just because it sits perceptually close to a neighbour.
 *
 * ``weights`` (per centroid, e.g. pixel-area coverage) drive the ranking;
 * omitted ⇒ every segment counts as one (rank by segment count).
 *
 * @returns Up to ``m`` canonical ``#rrggbb`` inks, most-dominant first. Empty
 *   when the pool or the centroid list is empty.
 */
export function chooseInkPalette(
  centroids: readonly string[],
  pool: readonly string[],
  m: number,
  weights?: readonly number[],
): string[] {
  const target = Math.max(1, Math.floor(m))
  if (!pool.length || !centroids.length) return []
  // Snap each segment to its nearest available ink, accumulating area per ink.
  const coverageByInk = new Map<string, number>()
  centroids.forEach((c, i) => {
    const ink = nearestPoolHex(c, pool)
    if (!ink) return
    const w = Math.max(0, weights?.[i] ?? 1)
    coverageByInk.set(ink, (coverageByInk.get(ink) ?? 0) + w)
  })
  // Keep the M inks covering the most area; minor inks' segments fold onto the
  // nearest survivor in the caller's snap.
  return [...coverageByInk.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, target)
    .map(([ink]) => ink)
}

export interface PoolAssignmentItem {
  /** Cluster centroid the assignment is computed from. */
  sourceHex: string
  /**
   * Operator-pinned ink (manual override). The item keeps its pin (the
   * result slot is ``null``) but the matching pool entry is consumed so
   * the auto rows spread over the remaining inks.
   */
  pinnedHex?: string | null
}

/**
 * Frontend mirror of the backend's ``assign_pool_inks``: snap each item
 * to its perceptually-nearest pool ink (CIE Lab ΔE 2000, **reuse
 * allowed**). Pinned items keep their pin (result slot ``null``).
 *
 * Reuse over distinctness is deliberate: two clusters that are both
 * closest to the same ink both draw that ink (merged into one layer
 * downstream) instead of one being scattered onto an unrelated ink to
 * look "distinct". A pool that doesn't span the image's colours
 * therefore collapses onto the closest inks rather than painting greens
 * as blue/black. When the image genuinely has N distinct colours and the
 * pool spans them, nearest-match already yields N distinct inks; to use
 * more pens, raise the segmentation colour count.
 *
 * @returns One entry per item, aligned by index: the canonical assigned
 *   hex for auto items, ``null`` for pinned items (keep the pin) or
 *   when the pool is empty.
 */
export function assignPoolHexes(
  items: readonly PoolAssignmentItem[],
  pool: readonly string[],
): (string | null)[] {
  const result: (string | null)[] = items.map(() => null)
  if (!pool.length) return result
  const poolHex = pool.map((h) => canonicalHex(h))
  for (let i = 0; i < items.length; i++) {
    // Pinned items keep their manual override — leave the slot null.
    if (items[i]!.pinnedHex) continue
    result[i] = nearestPoolHex(items[i]!.sourceHex, poolHex)
  }
  return result
}
