import DOMPurify from 'dompurify'

// Shared LRU cache for DOMPurify.sanitize results on SVG payloads. The full
// DOM walk is expensive on Pi-class hardware (10k+ paths in dense plots);
// cachable call sites — preview computeds that re-fire on every store tick,
// thumbnail row rendering — pay it once per distinct SVG instead of per
// dependency invalidation.
const CACHE_MAX = 64
const _cache = new Map<string, string>()

const SVG_PROFILES = { USE_PROFILES: { svg: true, svgFilters: true } } as const

// Editor-preview profile: the SVG profile above PLUS ``inkscape:label`` on
// the per-layer ``<g>`` groups. The preview pane reads that label to drive
// its client-side opacity / hide overlay (EditPreviewPane.applyOpacityOverlay);
// the default profile strips namespaced attributes, which would silently
// break the per-layer "hide this colour" toggle. ``inkscape:label`` is an
// inert metadata string (no URL, no script), so allow-listing it is safe.
const PREVIEW_SVG_PROFILES = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_ATTR: ['inkscape:label'],
}
const _previewCache = new Map<string, string>()

function sanitizeCached(
  svg: string,
  cache: Map<string, string>,
  config: Parameters<typeof DOMPurify.sanitize>[1],
): string {
  if (!svg) return ''
  const cached = cache.get(svg)
  if (cached !== undefined) {
    // LRU touch: re-insert so it's the most-recent entry.
    cache.delete(svg)
    cache.set(svg, cached)
    return cached
  }
  const clean = DOMPurify.sanitize(svg, config) as string
  cache.set(svg, clean)
  if (cache.size > CACHE_MAX) {
    const oldest = cache.keys().next().value
    if (oldest !== undefined) cache.delete(oldest)
  }
  return clean
}

export function sanitizeSvgCached(svg: string): string {
  return sanitizeCached(svg, _cache, SVG_PROFILES)
}

// Sanitize an SVG bound for the editor preview's ``v-html`` — same hardening
// as ``sanitizeSvgCached`` but keeps ``inkscape:label`` so the per-layer
// overlay still works. This is the single trusted boundary used by
// ``SafeSvgHtml.vue``; nothing should reach a preview ``v-html`` without
// passing through it.
export function sanitizePreviewSvgCached(svg: string): string {
  return sanitizeCached(svg, _previewCache, PREVIEW_SVG_PROFILES)
}
