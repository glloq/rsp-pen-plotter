// @vitest-environment jsdom
// jsdom (not happy-dom): DOMPurify >= 3.4.11 mis-detects happy-dom nodes via its
// cross-realm instanceof hardening and mangles SVG output there; jsdom matches
// real-Chromium sanitizer behaviour.
// Regression guard for the watcher-lifetime bug.
// ``ensureWired`` registered ``watch()`` calls inside the first
// consumer's component scope, so Vue auto-stopped them when that
// component unmounted (= the modal closing). The idempotency flag
// then blocked re-installation on the next mount, leaving the
// singleton previewer with no watchers driving it: changing the
// algorithm did nothing, the placement-switch reset never fired, and
// stale state from the first session leaked into every subsequent
// one. The fix wraps the watcher installation in a detached
// ``effectScope(true)`` so they outlive any single component instance.

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { resetEditState } from './useEditState'
import { resetFileManager, useFileManager } from './useFileManager'
import { useJobStore } from '../stores/job'

const Harness = defineComponent({
  setup() {
    useFileManager()
    return () => h('div')
  },
})

function makeFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' })
}

describe('useFileManager — watchers survive component unmount', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('placement-switch watcher still fires after the first consumer unmounts', async () => {
    const store = useJobStore()
    store.placements = [
      {
        id: 'p1',
        source_file: 'a.png',
        source_mime: 'image/png',
        last_file: makeFile('a.png'),
        library_file_id: null,
        variants: [],
      } as never,
      {
        id: 'p2',
        source_file: 'b.png',
        source_mime: 'image/png',
        last_file: makeFile('b.png'),
        library_file_id: null,
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'

    // First mount installs the watchers (inside the detached scope).
    const first = mount(Harness)
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    // Pre-populate the singleton previewer's result to simulate a
    // completed /preview for p1.
    const fm = useFileManager()
    fm.previewer.previewResult.value = {
      svg: '<svg data-test-marker="p1-stale" />',
      elapsed_ms: 12,
      palette: [],
      warnings: [],
      cached: false,
    }
    expect(fm.previewSvg.value).toContain('p1-stale')

    // Unmount the first consumer. With the old code (watchers bound
    // to the component scope) Vue would auto-stop every watcher here
    // and the placement-switch reset below would silently no-op.
    first.unmount()
    await nextTick()

    // Switch placement. The detached watcher must fire and clear the
    // singleton previewer's stale result.
    store.selectedPlacementId = 'p2'
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    expect(fm.previewer.previewResult.value).toBeNull()
    expect(fm.previewSvg.value).toBe('')
  })

  it('file-load watcher still tags the singleton with the active placement id after a remount', async () => {
    const store = useJobStore()
    store.placements = [
      {
        id: 'p1',
        source_file: 'a.png',
        source_mime: 'image/png',
        last_file: makeFile('a.png'),
        library_file_id: null,
        variants: [],
      } as never,
      {
        id: 'p2',
        source_file: 'b.png',
        source_mime: 'image/png',
        last_file: makeFile('b.png'),
        library_file_id: null,
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'

    const first = mount(Harness)
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    const fm = useFileManager()
    expect(fm.selectedFilePlacementId.value).toBe('p1')

    // Tear down + remount simulates the modal closing and reopening.
    first.unmount()
    await nextTick()
    const second = mount(Harness)
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    // Switching placements has to update ``selectedFilePlacementId``
    // — that's the identity ``expertPreviewSvg`` uses to decide
    // whether the singleton svg belongs to the active placement.
    store.selectedPlacementId = 'p2'
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    expect(fm.selectedFile.value?.name).toBe('b.png')
    expect(fm.selectedFilePlacementId.value).toBe('p2')

    second.unmount()
  })
})
