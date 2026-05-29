// @vitest-environment happy-dom
import { setActivePinia, createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useUploadsStore } from './uploads'
import { useLibraryStore } from './library'
import type { LibraryFileDetail } from '../api/client'

function svgFile(name: string): File {
  // A few bytes so it passes the non-empty check; .svg extension passes the
  // type check. happy-dom's File reports ``size`` from the blob parts.
  return new File(['<svg/>'], name, { type: 'image/svg+xml' })
}

function detail(name: string, warnings: string[] = []): LibraryFileDetail {
  return {
    file_id: `id-${name}`,
    sha256: `sha-${name}`,
    source_file: name,
    source_mime: 'image/svg+xml',
    size_bytes: 6,
    layer_count: 1,
    folder: '',
    created_at: new Date().toISOString(),
    svg: '<svg/>',
    layers: [],
    warnings,
    upload_metadata: {},
  }
}

describe('uploads store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('runs a batch to completion and marks new vs existing files', async () => {
    const library = useLibraryStore()
    vi.spyOn(library, 'upload').mockImplementation(async (file: File) => ({
      file: detail(file.name),
      existing: file.name === 'b.svg',
    }))

    const uploads = useUploadsStore()
    uploads.start([svgFile('a.svg'), svgFile('b.svg')])
    expect(uploads.visible).toBe(true)
    await flushPromises()

    expect(uploads.active).toBe(false)
    const byName = Object.fromEntries(uploads.items.map((i) => [i.name, i.status]))
    expect(byName['a.svg']).toBe('done')
    expect(byName['b.svg']).toBe('existing')
    expect(uploads.doneCount).toBe(2)
  })

  it('surfaces converter warnings as a per-file count', async () => {
    const library = useLibraryStore()
    vi.spyOn(library, 'upload').mockResolvedValue({
      file: detail('w.svg', ['text not embedded', 'clipped path']),
      existing: false,
    })

    const uploads = useUploadsStore()
    uploads.start([svgFile('w.svg')])
    await flushPromises()

    expect(uploads.hasWarnings).toBe(true)
    expect(uploads.items[0]!.warningCount).toBe(2)
  })

  it('rejects invalid files up front without calling upload', async () => {
    const library = useLibraryStore()
    const spy = vi.spyOn(library, 'upload')

    const uploads = useUploadsStore()
    // No extension → invalidType, and the store never reaches the network.
    uploads.start([new File(['x'], 'notes', { type: 'text/plain' })])
    await flushPromises()

    expect(spy).not.toHaveBeenCalled()
    expect(uploads.items[0]!.status).toBe('error')
  })

  it('marks a file cancelled when its upload is aborted', async () => {
    const library = useLibraryStore()
    // Simulate the library store's cancellation contract: it resolves null
    // when the AbortSignal fired.
    vi.spyOn(library, 'upload').mockImplementation(
      async (_file: File, opts) =>
        new Promise((resolve) => {
          opts?.signal?.addEventListener('abort', () => resolve(null))
        }),
    )

    const uploads = useUploadsStore()
    uploads.start([svgFile('slow.svg')])
    await flushPromises()
    expect(uploads.items[0]!.status).toBe('uploading')

    uploads.cancelAll()
    await flushPromises()
    expect(uploads.items[0]!.status).toBe('cancelled')
    expect(uploads.active).toBe(false)
  })
})
