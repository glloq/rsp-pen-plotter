import DOMPurify from 'dompurify'

// Shared LRU cache for DOMPurify.sanitize results on SVG payloads. The full
// DOM walk is expensive on Pi-class hardware (10k+ paths in dense plots);
// cachable call sites — preview computeds that re-fire on every store tick,
// thumbnail row rendering — pay it once per distinct SVG instead of per
// dependency invalidation.
const CACHE_MAX = 64
const _cache = new Map<string, string>()

const SVG_PROFILES = { USE_PROFILES: { svg: true, svgFilters: true } } as const

export function sanitizeSvgCached(svg: string): string {
  if (!svg) return ''
  const cached = _cache.get(svg)
  if (cached !== undefined) {
    // LRU touch: re-insert so it's the most-recent entry.
    _cache.delete(svg)
    _cache.set(svg, cached)
    return cached
  }
  const clean = DOMPurify.sanitize(svg, SVG_PROFILES)
  _cache.set(svg, clean)
  if (_cache.size > CACHE_MAX) {
    const oldest = _cache.keys().next().value
    if (oldest !== undefined) _cache.delete(oldest)
  }
  return clean
}
