// @vitest-environment jsdom
// jsdom (not happy-dom): DOMPurify >= 3.4.11 mis-detects happy-dom nodes via its
// cross-realm instanceof hardening and mangles SVG output there; jsdom matches
// real-Chromium sanitizer behaviour.
// Regression guard for the "switching placements still shows the
// previous preview SVG" bug. The singleton previewer caches the last
// /preview response; without an explicit clear on placement switch
// the V2 modal forwards a stale SVG to EditPreviewPane until the new
// placement's /preview round-trip lands.

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { resetEditState } from './useEditState'
import { resetFileManager, useFileManager } from './useFileManager'
import { useJobStore } from '../stores/job'

const Harness = defineComponent({
  setup() {
    const fm = useFileManager()
    return { fm }
  },
  render() {
    return h('div')
  },
})

function makeFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' })
}

describe('useFileManager — placement switch resets previewer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('clears previewResult when selectedPlacementId changes', async () => {
    const store = useJobStore()
    store.placements = [
      {
        id: 'p1',
        source_file: 'a.png',
        last_file: makeFile('a.png'),
        library_file_id: null,
        variants: [],
      } as never,
      {
        id: 'p2',
        source_file: 'b.png',
        last_file: makeFile('b.png'),
        library_file_id: null,
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'

    const wrapper = mount(Harness)
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    const fm = wrapper.vm.fm
    // Simulate a successful /preview response that landed before the
    // operator switched placements. The svg + palette mirror what the
    // V2 modal forwards to EditPreviewPane.
    fm.previewer.previewResult.value = {
      svg: '<svg data-test-marker="stale" />',
      elapsed_ms: 12,
      palette: [],
      warnings: [],
      cached: false,
    }
    expect(fm.previewSvg.value).toContain('stale')

    // Operator picks a different placement in FilesPane.
    store.selectedPlacementId = 'p2'
    // Allow the async watcher (rehydrate + ensureSelectedFile) to run.
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    // The stale preview must be gone — otherwise the V2 modal would
    // keep showing the previous image's conversion until the new
    // placement's /preview returns.
    expect(fm.previewer.previewResult.value).toBeNull()
    expect(fm.previewSvg.value).toBe('')
  })
})
