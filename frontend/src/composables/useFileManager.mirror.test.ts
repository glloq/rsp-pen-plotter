// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { resetEditState, useEditState } from './useEditState'
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

describe('useFileManager → useEditState mirroring', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    // happy-dom may lack createObjectURL
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('populates edit.previewUrl when a bitmap placement has an in-memory last_file', async () => {
    const store = useJobStore()
    const file = makeFile('photo.png')
    // Seed a placement that owns the file bytes (post-upload state).
    store.placements = [
      {
        id: 'p1',
        source_file: 'photo.png',
        last_file: file,
        library_file_id: null,
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'

    mount(Harness)
    // Let the initial queueMicrotask (ensureSelectedFile) + watchers run.
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    await nextTick()

    const edit = useEditState()
    expect(edit.selectedFile.value?.name).toBe('photo.png')
    expect(edit.kind.value).toBe('bitmap')
    expect(edit.previewUrl.value).toBeTruthy()
  })
})
