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

function deltaE2000(lab1: [number, number, number], lab2: [number, number, number]): number {
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
 * Frontend mirror of the backend's ``auto_assign_layer_colors``: match
 * each item to a pool ink, keeping inks **distinct** while unused pool
 * entries remain.
 *
 * A plain per-item nearest-match collapses distinct clusters onto the
 * same ink as soon as the cluster count grows past the pool's spread
 * (6 clusters / 4 pens → 2-3 visible colours). Items are matched
 * greedily by ascending ΔE 2000 without reusing a pool entry; once the
 * pool is exhausted the leftovers fall back to plain nearest-match.
 * Duplicate pool entries count as that many uses (two identical pens
 * really can serve two layers).
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
  const poolLab = poolHex.map((h) => hexToLab(h))
  const available = poolHex.map(() => true)

  const autoIndices: number[] = []
  for (let i = 0; i < items.length; i++) {
    const pinned = items[i]!.pinnedHex
    if (pinned) {
      const key = canonicalHex(pinned)
      const j = poolHex.findIndex((h, idx) => available[idx] && h === key)
      if (j >= 0) available[j] = false
      continue
    }
    autoIndices.push(i)
  }
  if (!autoIndices.length) return result

  // Globally-greedy unique matching: smallest remaining (item, ink) ΔE
  // wins. The pair list is tiny (≤16 clusters × a pen rack), so the
  // full sort costs nothing.
  const pairs: Array<{ row: number; col: number; d: number }> = []
  for (let r = 0; r < autoIndices.length; r++) {
    const lab = hexToLab(items[autoIndices[r]!]!.sourceHex)
    for (let c = 0; c < poolLab.length; c++) {
      pairs.push({ row: r, col: c, d: deltaE2000(lab, poolLab[c]!) })
    }
  }
  pairs.sort((a, b) => a.d - b.d)
  const rowDone = autoIndices.map(() => false)
  let remaining = autoIndices.length
  for (const { row, col } of pairs) {
    if (remaining === 0 || !available.includes(true)) break
    if (rowDone[row] || !available[col]) continue
    result[autoIndices[row]!] = poolHex[col]!
    rowDone[row] = true
    available[col] = false
    remaining -= 1
  }
  // Pool exhausted → plain nearest for whoever is left.
  for (let r = 0; r < autoIndices.length; r++) {
    if (!rowDone[r]) {
      result[autoIndices[r]!] = nearestPoolHex(items[autoIndices[r]!]!.sourceHex, poolHex)
    }
  }
  return result
}
