// @vitest-environment happy-dom
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({ api: { get: vi.fn() } }))

import { api } from '../api/client'
import { useAlgorithmsStore } from './algorithms'

const validManifest = {
  meta: {
    domain: 'algorithms',
    manifest_version: 1,
    schema_semver: '0.1.0',
    generated_at: '2026-05-27T22:00:00Z',
    deprecations: [],
    feature_flags: {},
  },
  entries: [
    {
      id: 'stippling',
      version: 1,
      deprecated: false,
      name: 'stippling',
      description: 'dots',
      kind: 'fill',
      complexity: 'medium',
      params: { type: 'object' },
      recommended_presets: [],
    },
    {
      id: 'crosshatch',
      version: 1,
      deprecated: false,
      name: 'crosshatch',
      description: 'hatched lines',
      kind: 'fill',
      complexity: 'medium',
      params: { type: 'object' },
      recommended_presets: [],
    },
  ],
}

describe('useAlgorithmsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.mocked(api.get).mockReset()
  })

  it('loads entries from the manifest endpoint and flips loaded=true', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: validManifest })
    const store = useAlgorithmsStore()
    expect(store.loaded).toBe(false)
    await store.refresh()
    expect(store.loaded).toBe(true)
    expect(store.entries.length).toBe(2)
    expect(store.source).toBe('live')
    expect(store.fromFallback).toBe(false)
  })

  it('exposes a legacy AlgorithmInfo[] shape via list', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: validManifest })
    const store = useAlgorithmsStore()
    await store.refresh()
    const names = store.list.map((a) => a.name)
    expect(names).toEqual(['stippling', 'crosshatch'])
    expect(store.list[0]).toMatchObject({
      name: 'stippling',
      complexity: 'medium',
      kind: 'fill',
    })
  })

  it('falls back to snapshot when network errors out and flags fromFallback', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('network down'))
    const store = useAlgorithmsStore()
    await store.refresh()
    expect(store.source).toBe('snapshot')
    expect(store.fromFallback).toBe(true)
    expect(store.lastError).toBeInstanceOf(Error)
    expect(store.entries.length).toBeGreaterThan(0)
  })

  it('byId is keyed by entry.id', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: validManifest })
    const store = useAlgorithmsStore()
    await store.refresh()
    expect(store.byId.get('stippling')?.complexity).toBe('medium')
    expect(store.byId.get('does-not-exist')).toBeUndefined()
  })
})
