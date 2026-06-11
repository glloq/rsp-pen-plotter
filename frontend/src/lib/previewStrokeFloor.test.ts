// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'

import { applyPreviewStrokeFloor } from './previewStrokeFloor'

function makeSvg(): SVGSVGElement {
  const host = document.createElement('div')
  host.innerHTML =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">' +
    '<g stroke-width="0.8"><polyline points="0,0 10,10"/></g>' +
    '<g stroke-width="6"><polyline points="0,0 10,10"/></g>' +
    '<g><circle r="2"/></g>' +
    '</svg>'
  return host.querySelector('svg') as SVGSVGElement
}

describe('applyPreviewStrokeFloor', () => {
  it('floors sub-pixel strokes at the display scale, leaves thick ones alone', () => {
    const svg = makeSvg()
    // 800 viewBox units shown over 400 device px → 1 device px = 2 units;
    // 0.8 device px floor = 1.6 units. The hairline (0.8) must rise to
    // 1.6, the 6-unit stroke stays.
    applyPreviewStrokeFloor(svg, 400)
    const groups = svg.querySelectorAll('[stroke-width]')
    expect(groups[0]!.getAttribute('stroke-width')).toBe('1.6')
    expect(groups[1]!.getAttribute('stroke-width')).toBe('6')
  })

  it('restores the true width when zooming makes the floor irrelevant (idempotent)', () => {
    const svg = makeSvg()
    applyPreviewStrokeFloor(svg, 400) // floored to 1.6
    // Zoomed in 8×: 3200 device px → floor 0.2 units < original 0.8 →
    // the stashed original width comes back exactly.
    applyPreviewStrokeFloor(svg, 3200)
    const groups = svg.querySelectorAll('[stroke-width]')
    expect(groups[0]!.getAttribute('stroke-width')).toBe('0.8')
    // Repeated application never compounds.
    applyPreviewStrokeFloor(svg, 400)
    applyPreviewStrokeFloor(svg, 400)
    expect(groups[0]!.getAttribute('stroke-width')).toBe('1.6')
  })

  it('no-ops without layout or viewBox', () => {
    const svg = makeSvg()
    applyPreviewStrokeFloor(svg, 0)
    expect(svg.querySelectorAll('[stroke-width]')[0]!.getAttribute('stroke-width')).toBe('0.8')
    svg.removeAttribute('viewBox')
    applyPreviewStrokeFloor(svg, 400)
    expect(svg.querySelectorAll('[stroke-width]')[0]!.getAttribute('stroke-width')).toBe('0.8')
  })
})
