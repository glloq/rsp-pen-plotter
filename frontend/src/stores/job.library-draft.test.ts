// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// createPlacementFromLibrary fetches a LibraryFileDetail via the API
// client; we stub that so the test focuses purely on the
// placement-visibility behaviour.
vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    getLibraryFile: vi.fn().mockResolvedValue({
      file_id: 'lib-1',
      source_file: 'square.png',
      source_mime: 'image/png',
      rerenderable: true,
      svg: '<svg/>',
      layers: [],
      upload_warnings: [],
      upload_metadata: {},
    }),
  }
})

import { useJobStore } from './job'

describe('library-draft placements (Edit from library does not put on sheet)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('createPlacementFromLibrary asDraft=true hides the placement from visiblePlacements', async () => {
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1', undefined, {
      asDraft: true,
    })
    expect(id).toBeTruthy()
    expect(store.placements.length).toBe(1)
    expect(store.placements[0]?.is_library_draft).toBe(true)
    expect(store.visiblePlacements.length).toBe(0)
  })

  it('without asDraft, the placement is immediately visible on the sheet', async () => {
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1')
    expect(id).toBeTruthy()
    expect(store.placements[0]?.is_library_draft).toBeFalsy()
    expect(store.visiblePlacements.length).toBe(1)
  })

  it('materializeLibraryDraft promotes a draft to visible', async () => {
    const store = useJobStore()
    const id = await store.createPlacementFromLibrary('lib-1', undefined, {
      asDraft: true,
    })
    expect(store.visiblePlacements.length).toBe(0)
    store.materializeLibraryDraft(id!)
    expect(store.visiblePlacements.length).toBe(1)
    expect(store.placements[0]?.is_library_draft).toBe(false)
  })
})
