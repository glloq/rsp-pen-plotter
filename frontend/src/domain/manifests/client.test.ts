// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/client', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '../../api/client'
import {
  AlgorithmsManifestSchema,
  ManifestVersionMismatchError,
  assertSupportedVersion,
} from './schemas'
import { _internal, fetchAlgorithmsManifest } from './client'

const validPayload = {
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
      kind: 'fill' as const,
      complexity: 'medium' as const,
      params: { type: 'object' },
      recommended_presets: [],
    },
  ],
}

describe('manifest client', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.mocked(api.get).mockReset()
  })
  afterEach(() => {
    window.localStorage.clear()
  })

  it('returns live data when the backend responds', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: validPayload })
    const result = await fetchAlgorithmsManifest()
    expect(result.source).toBe('live')
    expect(result.data.entries[0]?.id).toBe('stippling')
  })

  it('caches a successful live fetch in localStorage', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: validPayload })
    await fetchAlgorithmsManifest()
    const cached = _internal.readCache('algorithms')
    expect(cached).toBeTruthy()
  })

  it('falls back to localStorage cache when the backend errors out', async () => {
    _internal.writeCache('algorithms', validPayload)
    vi.mocked(api.get).mockRejectedValueOnce(new Error('network down'))
    const result = await fetchAlgorithmsManifest()
    expect(result.source).toBe('cache')
    expect(result.data.entries[0]?.id).toBe('stippling')
    expect(result.error).toBeDefined()
  })

  it('falls back to build-time snapshot when neither live nor cache work', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('network down'))
    const result = await fetchAlgorithmsManifest()
    expect(result.source).toBe('snapshot')
    expect(result.data.entries.length).toBeGreaterThan(0)
  })

  it('rejects unsupported manifest_version', async () => {
    const future = {
      ...validPayload,
      meta: { ...validPayload.meta, manifest_version: 999 },
    }
    vi.mocked(api.get).mockResolvedValueOnce({ data: future })
    const result = await fetchAlgorithmsManifest()
    // Future version is rejected -> falls back to snapshot.
    expect(result.source).toBe('snapshot')
    expect(result.error).toBeInstanceOf(ManifestVersionMismatchError)
  })

  it('rejects malformed payloads at the zod boundary', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { meta: { not: 'a-real-envelope' }, entries: [] },
    })
    const result = await fetchAlgorithmsManifest()
    expect(result.source).toBe('snapshot')
    expect(result.error).toBeDefined()
  })
})

describe('schema helpers', () => {
  it('AlgorithmsManifestSchema rejects extra unknown shapes gracefully', () => {
    const r = AlgorithmsManifestSchema.safeParse({ meta: {}, entries: [] })
    expect(r.success).toBe(false)
  })

  it('assertSupportedVersion is a no-op for unknown domains', () => {
    expect(() => assertSupportedVersion('mystery', 42)).not.toThrow()
  })
})
