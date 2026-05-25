import { setActivePinia, createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { useLibraryStore } from './library'

describe('library integrity', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('starts empty and flips to populated after refreshIntegrity', async () => {
    // The store mirrors the backend's GET /files/integrity (lot L4). On
    // boot it should treat "no issues" as the healthy default — banner
    // hidden — and only fill in when the scan returns issues.
    const lib = useLibraryStore()
    expect(lib.integrityIssues).toEqual([])
    expect(lib.brokenFileIds.size).toBe(0)

    vi.spyOn(client, 'getFilesIntegrity').mockResolvedValue({
      checked: 5,
      rerenderable: 3,
      issues: [
        { file_id: 'abc', source_file: 'logo.png', reason: 'missing_bitmap_options' },
        { file_id: 'def', source_file: 'plan.pdf', reason: 'missing_original_bytes' },
      ],
    })

    await lib.refreshIntegrity()
    expect(lib.integrityIssues).toHaveLength(2)
    expect(lib.isFileBroken('abc')).toBe(true)
    expect(lib.isFileBroken('def')).toBe(true)
    expect(lib.isFileBroken('xyz')).toBe(false)
  })

  it('keeps the previous report on transient fetch failure', async () => {
    // A blip in network must not blank an existing report — the
    // operator would otherwise think the issues were resolved while
    // the underlying files are still broken on disk.
    const lib = useLibraryStore()
    vi.spyOn(client, 'getFilesIntegrity').mockResolvedValueOnce({
      checked: 1,
      rerenderable: 1,
      issues: [{ file_id: 'abc', source_file: 'a.png', reason: 'missing_bitmap_options' }],
    })
    await lib.refreshIntegrity()
    expect(lib.integrityIssues).toHaveLength(1)

    vi.spyOn(client, 'getFilesIntegrity').mockRejectedValueOnce(new Error('network'))
    await lib.refreshIntegrity()
    expect(lib.integrityIssues).toHaveLength(1) // unchanged
  })
})
