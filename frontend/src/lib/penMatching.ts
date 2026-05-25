// Pen ↔ colour matching utilities.
//
// Operators routinely segment a photo into N clusters that don't line
// up with the pens installed in the magazine — the multicolour layer
// list then needs to (a) suggest the nearest pen for each cluster and
// (b) warn when the closest pen is still too far away to read as the
// target colour. A perceptual distance is good enough for the small
// pen palettes the operator deals with (<= 16 entries); we use plain
// RGB Euclidean for the math and convert the result into a 0..100
// "distance score" that maps onto a soft / medium / hard threshold.
//
// Why not Lab ΔE? The pen palettes are small enough that the extra
// gamut-correctness Lab gives buys nothing — the operator is choosing
// between visibly different inks, not subtle Pantone neighbours. RGB
// Euclidean has a clean closed form, no library deps, and the rank
// order matches Lab for the colour pairs that matter here (red vs
// orange, blue vs purple, etc.).

export interface PenSlotLike {
  index: number
  color: string
  installed?: boolean
}

export interface PenMatch {
  // The pen slot closest to the target colour. May be null when no pen
  // is installed at all — callers render an "install a pen" warning.
  pen: PenSlotLike | null
  // 0..100 perceptual distance. 0 = exact match, ~30 = noticeable, 60+
  // = the wrong ink. Use ``severity`` for the UI gate.
  distance: number
  severity: 'exact' | 'close' | 'far' | 'wrong' | 'none'
}

const HEX_RE = /^#([0-9a-fA-F]{6})$/

function parseHex(hex: string): [number, number, number] | null {
  const match = HEX_RE.exec(hex.trim())
  if (!match) return null
  const n = parseInt(match[1]!, 16)
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]
}

// RGB Euclidean distance normalised to 0..100 (max possible is the
// black-to-white diagonal, sqrt(3) * 255). Squared distance avoids the
// sqrt for the rank-by-min loop; we only convert once at the end.
function rgbDistance(a: [number, number, number], b: [number, number, number]): number {
  const dr = a[0]! - b[0]!
  const dg = a[1]! - b[1]!
  const db = a[2]! - b[2]!
  const maxSq = 3 * 255 * 255
  return Math.sqrt((dr * dr + dg * dg + db * db) / maxSq) * 100
}

// Find the installed pen whose colour is closest to ``target``. Returns
// the nearest match plus a severity classification so the layer card
// can render a green / amber / red badge without re-thresholding.
export function nearestPen(target: string, pens: PenSlotLike[]): PenMatch {
  const installed = pens.filter((p) => p.installed !== false && parseHex(p.color))
  if (installed.length === 0) {
    return { pen: null, distance: 100, severity: 'none' }
  }
  const targetRgb = parseHex(target)
  if (!targetRgb) {
    return { pen: installed[0]!, distance: 100, severity: 'wrong' }
  }
  let best: PenSlotLike = installed[0]!
  let bestDist = Infinity
  for (const pen of installed) {
    const rgb = parseHex(pen.color)
    if (!rgb) continue
    const d = rgbDistance(targetRgb, rgb)
    if (d < bestDist) {
      bestDist = d
      best = pen
    }
  }
  let severity: PenMatch['severity']
  if (bestDist < 3) severity = 'exact'
  else if (bestDist < 12) severity = 'close'
  else if (bestDist < 28) severity = 'far'
  else severity = 'wrong'
  return { pen: best, distance: bestDist, severity }
}
