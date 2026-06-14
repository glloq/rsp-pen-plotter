import { describe, expect, it } from 'vitest'
import { recolorPreviewSvg } from './previewRecolor'

describe('recolorPreviewSvg', () => {
  it('rewrites fill and stroke hexes to their mapped pool ink', () => {
    const svg =
      '<g fill="#3a5f2c"><path/></g><g stroke="#1b3a6f"><path/></g>'
    const map = new Map([
      ['#3a5f2c', '#808080'],
      ['#1b3a6f', '#001f5b'],
    ])
    expect(recolorPreviewSvg(svg, map)).toBe(
      '<g fill="#808080"><path/></g><g stroke="#001f5b"><path/></g>',
    )
  })

  it('matches hex case-insensitively', () => {
    const svg = '<g fill="#3A5F2C"/>'
    const map = new Map([['#3a5f2c', '#808080']])
    expect(recolorPreviewSvg(svg, map)).toBe('<g fill="#808080"/>')
  })

  it('leaves colours absent from the map untouched (e.g. the paper rect)', () => {
    const svg = '<rect fill="#ffffff"/><g stroke="#3a5f2c"/>'
    const map = new Map([['#3a5f2c', '#808080']])
    expect(recolorPreviewSvg(svg, map)).toBe('<rect fill="#ffffff"/><g stroke="#808080"/>')
  })

  it('maps each token once from the original — no double remap when a centroid maps onto another centroid value', () => {
    // #aaaaaa → #bbbbbb and #bbbbbb → #cccccc. A naive sequential
    // string-replace would turn the first group into #cccccc; the
    // single-pass replacer must keep it at #bbbbbb.
    const svg = '<g fill="#aaaaaa"/><g fill="#bbbbbb"/>'
    const map = new Map([
      ['#aaaaaa', '#bbbbbb'],
      ['#bbbbbb', '#cccccc'],
    ])
    expect(recolorPreviewSvg(svg, map)).toBe('<g fill="#bbbbbb"/><g fill="#cccccc"/>')
  })

  it('returns the SVG unchanged for an empty map', () => {
    const svg = '<g fill="#3a5f2c"/>'
    expect(recolorPreviewSvg(svg, new Map())).toBe(svg)
  })
})
