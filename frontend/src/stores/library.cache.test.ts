import { setActivePinia, createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useLibraryStore } from './library'

// The detail cache holds a full SVG per entry, so it is FIFO-capped to keep
// memory bounded over a long browsing session. These tests pin the cap +
// the safe-miss contract (eviction just re-fetches).
describe('library detail cache eviction', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  function stubDetail(fileId: string) {
    return {
      file_id: fileId,
      source_file: `${fileId}.svg`,
      source_mime: 'image/svg+xml',
      rerenderable: false,
      svg: `<svg id="${fileId}"/>`,
      layers: [],
      upload_warnings: [],
      upload_metadata: {},
    } as unknown as Awaited<ReturnType<typeof client.getLibraryFile>>
  }

  it('evicts the oldest entry once the cap is exceeded', async () => {
    const lib = useLibraryStore()
    const spy = vi
      .spyOn(client, 'getLibraryFile')
      .mockImplementation(async (id: string) => stubDetail(id))

    // Cap is 40; load 41 distinct files so the first one is evicted.
    for (let i = 0; i < 41; i++) {
      await lib.ensureDetail(`f${i}`)
    }

    // Oldest (f0) evicted, newest (f40) retained.
    expect(lib.getDetail('f0')).toBeNull()
    expect(lib.getDetail('f40')).not.toBeNull()
    expect(spy).toHaveBeenCalledTimes(41)
  })

  it('re-fetches transparently after an eviction (safe miss)', async () => {
    const lib = useLibraryStore()
    const spy = vi
      .spyOn(client, 'getLibraryFile')
      .mockImplementation(async (id: string) => stubDetail(id))

    for (let i = 0; i < 41; i++) {
      await lib.ensureDetail(`f${i}`)
    }
    expect(lib.getDetail('f0')).toBeNull()

    // Asking again re-fetches and re-populates the cache.
    const again = await lib.ensureDetail('f0')
    expect(again?.file_id).toBe('f0')
    expect(lib.getDetail('f0')).not.toBeNull()
    expect(spy).toHaveBeenCalledTimes(42)
  })
})
