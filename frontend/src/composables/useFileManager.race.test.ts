// @vitest-environment happy-dom
// Regression guard for the placement-switch race in ``ensureSelectedFile``.
// When the operator clicks file B while file A's bytes are still being
// downloaded from /files/{id}/original, the late assignment used to
// clobber the singleton with File A while Placement B was active —
// surfacing as "the editor shows the wrong file at render".

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { resetEditState } from './useEditState'
import { resetFileManager, useFileManager } from './useFileManager'
import { useJobStore } from '../stores/job'

const downloads: Array<{
  fileId: string
  resolve: (file: File) => void
  reject: (err: unknown) => void
}> = []

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    downloadOriginalFile: vi.fn((fileId: string, name: string, mime: string) => {
      return new Promise<File>((resolve, reject) => {
        downloads.push({
          fileId,
          resolve: (file: File) => resolve(file),
          reject,
        })
        void name
        void mime
      })
    }),
  }
})

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

describe('useFileManager — ensureSelectedFile placement-switch race', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    downloads.length = 0
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('drops the late download result when the active placement changed mid-flight', async () => {
    const store = useJobStore()
    store.placements = [
      {
        id: 'p1',
        source_file: 'a.png',
        source_mime: 'image/png',
        last_file: null,
        library_file_id: 'lib-a',
        variants: [],
      } as never,
      {
        id: 'p2',
        source_file: 'b.png',
        source_mime: 'image/png',
        last_file: null,
        library_file_id: 'lib-b',
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'

    const wrapper = mount(Harness)
    // Let the initial queueMicrotask kick off ensureSelectedFile for p1.
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    expect(downloads.length).toBe(1)
    expect(downloads[0]!.fileId).toBe('lib-a')

    // Operator switches to p2 before p1's download has returned.
    store.selectedPlacementId = 'p2'
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    // The async watcher launched a second download — for p2.
    expect(downloads.length).toBe(2)
    expect(downloads[1]!.fileId).toBe('lib-b')

    // p1's network call finally lands. The placement is now p2, so the
    // result must be discarded — otherwise the singleton ends up with
    // file A's bytes while the modal is editing placement B.
    downloads[0]!.resolve(makeFile('a.png'))
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    const fm = wrapper.vm.fm
    expect(fm.selectedFile.value).toBeNull()

    // p2's call lands — that one IS for the active placement, so the
    // singleton accepts it.
    downloads[1]!.resolve(makeFile('b.png'))
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()

    expect(fm.selectedFile.value?.name).toBe('b.png')
  })
})
