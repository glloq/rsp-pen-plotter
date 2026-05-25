// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import FilesPane from './FilesPane.vue'

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
})
