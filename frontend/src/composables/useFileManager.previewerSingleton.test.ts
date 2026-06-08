// @vitest-environment happy-dom
// Regression guard for the per-call previewer instantiation bug.
// ``usePreviewScheduler`` used to be created fresh on every
// ``useFileManager()`` call — so when the V2 modal remounted on a
// placement switch, its ``fileManager.previewer`` became a NEW,
// unwired instance while the watchers kept writing to the FIRST
// instance. The modal's ``expertPreviewSvg`` then sat on an empty
// ref forever and could not refresh after a switch.

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { resetEditState } from './useEditState'
import { resetFileManager, useFileManager } from './useFileManager'

const First = defineComponent({
  setup() {
    const fm = useFileManager()
    return { fm }
  },
  render() {
    return h('div')
  },
})

const Second = defineComponent({
  setup() {
    const fm = useFileManager()
    return { fm }
  },
  render() {
    return h('div')
  },
})

describe('useFileManager — preview scheduler singleton', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('returns the same previewer instance across calls so consumers share previewResult', () => {
    const a = mount(First)
    const b = mount(Second)

    // Same object identity for the previewer itself AND for every
    // ref the modal forwards to EditPreviewPane. Identity matters
    // because Vue's reactivity tracks refs by reference — if B held
    // a different ``previewSvg`` ref than the wired watchers wrote
    // to, B would never see updates.
    expect(b.vm.fm.previewer).toBe(a.vm.fm.previewer)
    expect(b.vm.fm.previewSvg).toBe(a.vm.fm.previewSvg)
    expect(b.vm.fm.previewResult).toBe(a.vm.fm.previewResult)
  })

  it('mutating previewResult from one consumer surfaces in another', () => {
    const a = mount(First)
    const b = mount(Second)

    a.vm.fm.previewer.previewResult.value = {
      svg: '<svg data-test-marker="shared" />',
      elapsed_ms: 1,
      palette: [],
      warnings: [],
      cached: false,
    }

    expect(b.vm.fm.previewSvg.value).toContain('shared')
  })
})
