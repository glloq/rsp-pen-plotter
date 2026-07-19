// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import FilesPane from './FilesPane.vue'
import { useLibraryStore } from '../stores/library'
import type { LibraryFileRecord } from '../api/client'

// IntersectionObserver stub: happy-dom's own never fires, so capture the
// instances each FileListRow creates and let the test trigger them.
// Locally-typed to avoid the DOM IntersectionObserver* names (eslint
// no-undef).
type IOEntry = { isIntersecting: boolean; target: Element }
type IOCallback = (entries: IOEntry[], observer: unknown) => void

class MockIO {
  static instances: MockIO[] = []
  cb: IOCallback
  observed: Element[] = []
  constructor(cb: IOCallback) {
    this.cb = cb
    MockIO.instances.push(this)
  }
  observe(el: Element): void {
    this.observed.push(el)
  }
  disconnect(): void {}
  unobserve(): void {}
  takeRecords(): IOEntry[] {
    return []
  }
  fire(): void {
    this.cb(
      this.observed.map((target) => ({ isIntersecting: true, target })),
      this,
    )
  }
}

function makeRecord(id: string): LibraryFileRecord {
  return {
    file_id: id,
    sha256: id,
    source_file: `${id}.png`,
    source_mime: 'image/png',
    size_bytes: 2048,
    layer_count: 2,
    folder: '',
    created_at: '2026-06-01T00:00:00Z',
  }
}

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      files: {
        title: 'Files',
        addFile: 'Add a file',
        search: 'Search…',
        sort: 'Sort',
        sortName: 'Name',
        sortDate: 'Date',
        sortType: 'Type',
        sortAsc: 'Ascending',
        sortDesc: 'Descending',
        folder: 'Folder',
        allFolders: 'All folders',
        rootFolder: '(root)',
        newFolder: '+ New folder',
        empty: 'No files yet',
        emptyHint: 'Drag a file in to start.',
      },
      upload: {
        cancel: 'Cancel',
        converting: 'Converting…',
        layers: 'layers',
      },
    },
  },
})

function mountPane() {
  return mount(FilesPane, {
    global: { plugins: [i18n] },
  })
}

describe('FilesPane', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => {
    MockIO.instances = []
    vi.unstubAllGlobals()
  })

  it('renders the empty state when the library has no files', async () => {
    // The library store starts empty and FilesPane fetches /files on
    // mount — which fails under happy-dom without a server. The empty
    // state should render either way.
    const wrapper = mountPane()
    await nextTick()
    expect(wrapper.text()).toContain('No files yet')
  })

  it('renders the search input + sort + folder filter bar', async () => {
    const wrapper = mountPane()
    await nextTick()
    const search = wrapper.find('input[type="search"]')
    expect(search.exists()).toBe(true)
    const selects = wrapper.findAll('select')
    // Two selects: sortKey + folderFilter.
    expect(selects.length).toBeGreaterThanOrEqual(2)
  })

  it('exposes the "Add a file" upload button', async () => {
    const wrapper = mountPane()
    await nextTick()
    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('Add a file'))
    expect(addBtn).toBeDefined()
  })

  it('fetches a row’s thumbnail detail only once it scrolls into view (B3)', async () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const library = useLibraryStore()
    library.files = [makeRecord('f1'), makeRecord('f2')]
    const ensure = vi.spyOn(library, 'ensureDetail').mockResolvedValue(undefined as never)

    const wrapper = mountPane()
    await nextTick()
    // Both rows render, but nothing is fetched up front — the eager
    // "ensureDetail for every id" pass is gone.
    expect(wrapper.findAll('[data-test="file-row"]')).toHaveLength(2)
    expect(ensure).not.toHaveBeenCalled()

    // Scroll the rows into view → each lazily fetches its own detail.
    for (const io of MockIO.instances) io.fire()
    await nextTick()
    expect(ensure).toHaveBeenCalledWith('f1')
    expect(ensure).toHaveBeenCalledWith('f2')
  })

  it('row "Add to plan" places the file and lands on the Plan tab (UX Lot 1)', async () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const library = useLibraryStore()
    library.files = [makeRecord('f1')]
    vi.spyOn(library, 'ensureDetail').mockResolvedValue(undefined as never)
    const { useJobStore } = await import('../stores/job')
    const { useUiStore } = await import('../stores/ui')
    const job = useJobStore()
    const ui = useUiStore()
    ui.canvasTab = 'simulator'
    const create = vi.spyOn(job, 'createPlacementFromLibrary').mockResolvedValue('p1')
    const select = vi.spyOn(job, 'selectPlacement')

    const wrapper = mountPane()
    await nextTick()
    await wrapper.find('[data-test="file-row-add"]').trigger('click')
    await nextTick()
    expect(create).toHaveBeenCalledWith('f1')
    expect(select).toHaveBeenCalledWith('p1')
    expect(ui.canvasTab).toBe('sheet')
  })

  it('secondary actions live behind the row overflow menu', async () => {
    vi.stubGlobal('IntersectionObserver', MockIO)
    const library = useLibraryStore()
    library.files = [makeRecord('f1')]
    vi.spyOn(library, 'ensureDetail').mockResolvedValue(undefined as never)

    const wrapper = mountPane()
    await nextTick()
    // Move / remove are not rendered until the menu opens.
    expect(wrapper.find('[data-test="file-row-move"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="file-row-remove"]').exists()).toBe(false)
    await wrapper.find('[data-test="file-row-menu"]').trigger('click')
    expect(wrapper.find('[data-test="file-row-move"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="file-row-remove"]').exists()).toBe(true)
    // The primary actions stay directly visible.
    expect(wrapper.find('[data-test="file-row-add"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="file-row-edit"]').exists()).toBe(true)
  })
})
