// @vitest-environment jsdom
// jsdom (not happy-dom): DOMPurify >= 3.4.11 mis-detects happy-dom nodes via its
// cross-realm instanceof hardening and mangles SVG output there; jsdom matches
// real-Chromium sanitizer behaviour.
import { describe, expect, it } from 'vitest'

import { sanitizePreviewSvgCached, sanitizeSvgCached } from './sanitizeSvg'

describe('sanitizeSvgCached', () => {
  it('strips scripts and event handlers', () => {
    const out = sanitizeSvgCached(
      '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"><path d="M0 0"/></svg>',
    )
    expect(out.toLowerCase()).not.toContain('onload')
    expect(out).toContain('<svg')
  })

  it('drops the inkscape:label namespaced attribute (default profile)', () => {
    const out = sanitizeSvgCached(
      '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"><g inkscape:label="color-ff0000"/></svg>',
    )
    expect(out).not.toContain('inkscape:label')
  })

  it('returns empty for falsy input', () => {
    expect(sanitizeSvgCached('')).toBe('')
  })
})

describe('sanitizePreviewSvgCached', () => {
  it('keeps inkscape:label so the per-layer overlay can read it', () => {
    const out = sanitizePreviewSvgCached(
      '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"><g inkscape:label="color-ff0000"><path d="M0 0"/></g></svg>',
    )
    expect(out).toContain('inkscape:label="color-ff0000"')
  })

  it('still strips scripts even while allow-listing inkscape:label', () => {
    const out = sanitizePreviewSvgCached(
      '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    )
    expect(out.toLowerCase()).not.toContain('alert')
    expect(out.toLowerCase()).not.toContain('<script')
  })

  it('uses a cache (identical input returns an equal result)', () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    expect(sanitizePreviewSvgCached(svg)).toBe(sanitizePreviewSvgCached(svg))
  })
})
