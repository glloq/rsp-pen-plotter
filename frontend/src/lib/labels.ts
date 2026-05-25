/**
 * Format a raw layer label produced by the conversion pipeline into a
 * human-friendly object for the UI.
 *
 * Converters tag groups with stable machine-readable labels so the pipeline
 * stages stay decoupled (`text`, `image-1`, `color-ff0000`, `layer-1`). The
 * raw form is great for code but reads as line noise in the UI; this helper
 * peels off the kind and gives the renderer a nice label plus an optional
 * hex colour to use for a swatch.
 */
export type LayerKind = 'text' | 'image' | 'color' | 'generic'

export interface FormattedLayerLabel {
  kind: LayerKind
  display: string
  color?: string
  index?: number
}

const COLOR_RE = /^color-([0-9a-fA-F]{6})$/
const IMAGE_RE = /^image-(\d+)$/
const GENERIC_RE = /^layer-(\d+)$/

// Render a MIME string as a short uppercase badge — "image/svg+xml" → "SVG",
// "application/pdf" → "PDF". Used as the fallback label when no preview
// thumbnail is available for a library entry.
export function shortMime(mime: string): string {
  const subtype = mime.split('/')[1] ?? mime
  return subtype
    .replace(/\+.*$/, '')
    .replace(/^vnd\..+\./, '')
    .toUpperCase()
}

export function formatLayerLabel(id: string): FormattedLayerLabel {
  if (id === 'text') return { kind: 'text', display: 'Text' }
  const image = IMAGE_RE.exec(id)
  if (image) {
    const index = Number(image[1]!)
    return { kind: 'image', display: `Image ${index}`, index }
  }
  const color = COLOR_RE.exec(id)
  if (color) {
    const hex = color[1]!
    return { kind: 'color', display: `#${hex.toLowerCase()}`, color: `#${hex}` }
  }
  const generic = GENERIC_RE.exec(id)
  if (generic) return { kind: 'generic', display: `Layer ${generic[1]!}` }
  return { kind: 'generic', display: id }
}
