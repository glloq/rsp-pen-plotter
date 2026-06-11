// Palette-editing helpers shared by the PaletteCard and the colour-count
// slider (MultiColorMasterStyleParams).
//
// ``nextPadColor`` fixes the >4-colour collapse: growing a manual palette
// used to pad with repeated ``#888888`` chips — the duplicates rendered as
// a single backend layer (identical ``color-888888`` labels) AND the grey
// stole every mid-tone pixel from the real colours, so asking for 6
// colours displayed fewer than 4. Padding now hands out visually distinct,
// ink-like defaults the operator can recolour afterwards.

import { canonicalHex } from './penWidth'

// Distinct, plotter-ink-flavoured defaults. Grey stays first so the
// historical "add colour" behaviour (one grey chip) is preserved; the
// rest spreads across hue space and stays below the drop-background
// luminance threshold so a freshly-padded chip never silently vanishes
// as "paper". 16 entries match the colour-count slider's maximum.
export const PALETTE_PAD_COLORS: readonly string[] = [
  '#888888',
  '#000000',
  '#d32f2f',
  '#1976d2',
  '#388e3c',
  '#f57c00',
  '#7b1fa2',
  '#00838f',
  '#5d4037',
  '#c2185b',
  '#9e9d24',
  '#455a64',
  '#e64a19',
  '#303f9f',
  '#00796b',
  '#7e57c2',
]

/**
 * Pick the first pad colour not already present in ``existing``
 * (case-insensitive). Falls back to grey when the whole candidate list
 * is taken — at that point the operator owns 16+ distinct chips and a
 * duplicate grey is harmless (the backend merges identical entries).
 */
export function nextPadColor(existing: readonly string[]): string {
  const taken = new Set(existing.map((h) => canonicalHex(h)))
  for (const candidate of PALETTE_PAD_COLORS) {
    if (!taken.has(canonicalHex(candidate))) return candidate
  }
  return PALETTE_PAD_COLORS[0]!
}

/**
 * Rec.709 luminance of a hex colour in 0..1 — the same plain weighted
 * sum (no gamma linearisation) the backend's drop-background filter
 * applies, so frontend warnings agree with what actually gets dropped.
 */
export function rec709Luminance(hex: string): number {
  const body = canonicalHex(hex).slice(1)
  const r = parseInt(body.slice(0, 2), 16)
  const g = parseInt(body.slice(2, 4), 16)
  const b = parseInt(body.slice(4, 6), 16)
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}

/** Deduplicate a palette case-insensitively, keeping first occurrences. */
export function uniquePalette(palette: readonly string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const hex of palette) {
    const key = canonicalHex(hex)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(hex)
  }
  return out
}
