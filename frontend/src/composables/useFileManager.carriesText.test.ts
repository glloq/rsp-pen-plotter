// @vitest-environment happy-dom
// Guards the Text-tab gate. ``carriesText`` decides whether the editor
// offers its typography tools (font, Hershey re-render, page/block map)
// for the active source. It must be true for pure typography (.txt /
// .md) AND for mixed text+image documents (PDF / DOCX / ODT / RTF /
// HTML) — the latter regressed (a DOCX opened with only the bitmap
// tabs) — while staying false for pure vector graphics (SVG / DXF / …)
// and raster photos.

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

async function carriesTextFor(sourceFile: string): Promise<boolean> {
  const store = useJobStore()
  store.placements = [
    {
      id: 'p1',
      source_file: sourceFile,
      last_file: null,
      library_file_id: null,
      variants: [],
    } as never,
  ]
  store.selectedPlacementId = 'p1'
  const wrapper = mount(Harness)
  await new Promise((r) => setTimeout(r, 0))
  await nextTick()
  return wrapper.vm.fm.carriesText.value
}

describe('useFileManager — carriesText', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
    resetFileManager()
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake') as never
      globalThis.URL.revokeObjectURL = vi.fn() as never
    }
  })

  it('is true for typography sources (.txt / .md)', async () => {
    expect(await carriesTextFor('notes.txt')).toBe(true)
  })

  it('is true for mixed text+image documents (PDF / DOCX / ODT / RTF / HTML)', async () => {
    for (const name of ['report.pdf', 'letter.docx', 'memo.odt', 'note.rtf', 'page.html']) {
      resetFileManager()
      expect(await carriesTextFor(name)).toBe(true)
    }
  })

  it('is false for pure vector graphics and raster photos', async () => {
    for (const name of ['logo.svg', 'plan.dxf', 'art.eps', 'photo.jpg', 'scan.png']) {
      resetFileManager()
      expect(await carriesTextFor(name)).toBe(false)
    }
  })
})
