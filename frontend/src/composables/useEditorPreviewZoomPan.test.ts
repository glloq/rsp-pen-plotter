import { describe, expect, it, vi } from 'vitest'

import { useEditorPreviewZoomPan } from './useEditorPreviewZoomPan'

function wheel(deltaY: number): WheelEvent {
  return { deltaY, preventDefault: vi.fn() } as unknown as WheelEvent
}
function pointer(over: Partial<PointerEvent> = {}): PointerEvent {
  const target = {
    setPointerCapture: vi.fn(),
    releasePointerCapture: vi.fn(),
  }
  return {
    button: 0,
    clientX: 0,
    clientY: 0,
    pointerId: 1,
    currentTarget: target,
    ...over,
  } as unknown as PointerEvent
}

describe('useEditorPreviewZoomPan', () => {
  it('starts centred at 1× with an identity transform', () => {
    const zp = useEditorPreviewZoomPan()
    expect(zp.zoom.value).toBe(1)
    expect(zp.contentStyle.value.transform).toBe('translate(0px, 0px) scale(1)')
  })

  it('zooms in / out in 1.25 steps and resets', () => {
    const zp = useEditorPreviewZoomPan()
    zp.zoomIn()
    expect(zp.zoom.value).toBeCloseTo(1.25)
    zp.zoomOut()
    expect(zp.zoom.value).toBeCloseTo(1)
    zp.zoomIn()
    zp.resetView()
    expect(zp.zoom.value).toBe(1)
  })

  it('wheel up zooms in, wheel down zooms out, and preventDefault fires', () => {
    const zp = useEditorPreviewZoomPan()
    const up = wheel(-1)
    zp.onWheel(up)
    expect(up.preventDefault).toHaveBeenCalled()
    expect(zp.zoom.value).toBeCloseTo(1.15)
    zp.onWheel(wheel(1))
    expect(zp.zoom.value).toBeCloseTo(1)
  })

  it('clamps zoom to the [0.2, 16] range', () => {
    const zp = useEditorPreviewZoomPan()
    for (let i = 0; i < 50; i++) zp.zoomIn()
    expect(zp.zoom.value).toBe(16)
    for (let i = 0; i < 50; i++) zp.zoomOut()
    expect(zp.zoom.value).toBe(0.2)
  })

  it('drag-pans by the pointer delta and stops on pointer up', () => {
    const zp = useEditorPreviewZoomPan()
    zp.onPanStart(pointer({ clientX: 100, clientY: 100 }))
    expect(zp.panning.value).toBe(true)
    zp.onPanMove(pointer({ clientX: 130, clientY: 80 }))
    expect(zp.contentStyle.value.transform).toContain('translate(30px, -20px)')
    zp.onPanEnd(pointer())
    expect(zp.panning.value).toBe(false)
    // A move after release is ignored.
    zp.onPanMove(pointer({ clientX: 999, clientY: 999 }))
    expect(zp.contentStyle.value.transform).toContain('translate(30px, -20px)')
  })

  it('ignores non-primary/middle mouse buttons for panning', () => {
    const zp = useEditorPreviewZoomPan()
    zp.onPanStart(pointer({ button: 2 }))
    expect(zp.panning.value).toBe(false)
  })
})
