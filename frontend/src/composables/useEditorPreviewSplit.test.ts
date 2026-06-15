import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import { useEditorPreviewSplit } from './useEditorPreviewSplit'

// A pointer event whose currentTarget resolves a fake .sheet-outline with a
// known rect so updateSplit maths is deterministic.
function grabEvent(clientX: number): PointerEvent {
  const sheet = {
    getBoundingClientRect: () => ({ left: 0, width: 200 }) as DOMRect,
  }
  const target = {
    closest: (sel: string) => (sel === '.sheet-outline' ? sheet : null),
    setPointerCapture: vi.fn(),
    releasePointerCapture: vi.fn(),
  }
  return {
    clientX,
    pointerId: 1,
    currentTarget: target,
    stopPropagation: vi.fn(),
    preventDefault: vi.fn(),
  } as unknown as PointerEvent
}

describe('useEditorPreviewSplit', () => {
  it('starts at 50% with matching clip paths', () => {
    const split = useEditorPreviewSplit({
      viewMode: ref('split'),
      artworkFraction: ref(null),
    })
    expect(split.splitPercent.value).toBe(50)
    expect(split.splitPlotClip.value).toBe('inset(0 0 0 50%)')
    expect(split.splitSourceClip.value).toBe('inset(0 50% 0 0)')
  })

  it('drag sets the percent from the pointer position over the sheet', () => {
    const split = useEditorPreviewSplit({
      viewMode: ref('split'),
      artworkFraction: ref(null),
    })
    split.onSplitGrab(grabEvent(50)) // 50 / 200 = 25%
    expect(split.splitPercent.value).toBe(25)
    split.onSplitMove(grabEvent(150)) // 150 / 200 = 75%
    expect(split.splitPercent.value).toBe(75)
    split.onSplitRelease(grabEvent(150))
    // A move after release is ignored.
    split.onSplitMove(grabEvent(10))
    expect(split.splitPercent.value).toBe(75)
  })

  it('clamps the percent to 0..100', () => {
    const split = useEditorPreviewSplit({ viewMode: ref('split'), artworkFraction: ref(null) })
    split.onSplitGrab(grabEvent(500)) // past the right edge
    expect(split.splitPercent.value).toBe(100)
  })

  it('converts sheet-space percent into artwork space for the clips', () => {
    // Artwork only fills half the sheet width → the cut tracks the handle at
    // double the sheet-space percent (clamped).
    const split = useEditorPreviewSplit({
      viewMode: ref('split'),
      artworkFraction: ref({ w: 0.5, h: 1 }),
    })
    split.onSplitGrab(grabEvent(40)) // 40/200 = 20% of sheet
    // 20 / 0.5 = 40% of artwork.
    expect(split.splitPlotClip.value).toBe('inset(0 0 0 40%)')
  })

  it('resets to 50% when entering split mode', async () => {
    const viewMode = ref<'plot' | 'source' | 'split'>('plot')
    const split = useEditorPreviewSplit({ viewMode, artworkFraction: ref(null) })
    split.onSplitGrab(grabEvent(20)) // 10%
    expect(split.splitPercent.value).toBe(10)
    viewMode.value = 'split'
    await nextTick()
    // Watcher resets the sweep.
    expect(split.splitPercent.value).toBe(50)
  })
})
