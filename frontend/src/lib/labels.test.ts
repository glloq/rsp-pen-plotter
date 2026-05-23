import { describe, expect, it } from 'vitest'
import { formatLayerLabel } from './labels'

describe('formatLayerLabel', () => {
  it('formats the text layer', () => {
    expect(formatLayerLabel('text')).toEqual({ kind: 'text', display: 'Text' })
  })

  it('formats an image layer with its index', () => {
    expect(formatLayerLabel('image-3')).toEqual({
      kind: 'image',
      display: 'Image 3',
      index: 3,
    })
  })

  it('formats a colour layer with a CSS hex string', () => {
    expect(formatLayerLabel('color-FF00aa')).toEqual({
      kind: 'color',
      display: '#ff00aa',
      color: '#FF00aa',
    })
  })

  it('formats a generic numeric layer', () => {
    expect(formatLayerLabel('layer-7')).toEqual({ kind: 'generic', display: 'Layer 7' })
  })

  it('falls back to the raw id for unknown shapes', () => {
    expect(formatLayerLabel('my-custom-label')).toEqual({
      kind: 'generic',
      display: 'my-custom-label',
    })
  })
})
