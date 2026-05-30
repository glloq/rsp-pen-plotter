/**
 * Manifest client with build-time snapshot + localStorage fallback (roadmap A.7).
 *
 * Resolution order on each call:
 *   1. fetch `/manifests/{domain}` from the backend
 *   2. on network/parse/version error, load the entry cached in
 *      `localStorage` from the last successful fetch (if any)
 *   3. otherwise return the snapshot bundled at build time
 *
 * The caller is told via `source` which path was taken so a small UI
 * banner can warn the operator the manifest is stale.
 */
import { api } from '../../api/client'
import snapshot from './snapshot.json'
import {
  AlgorithmsManifestSchema,
  ManifestMetaSchema,
  type AlgorithmsManifest,
  ManifestVersionMismatchError,
  assertSupportedVersion,
} from './schemas'

const STORAGE_PREFIX = 'omniplot.manifest.'

export type ManifestSource = 'live' | 'cache' | 'snapshot'

export interface ManifestFetchResult<T> {
  data: T
  source: ManifestSource
  error?: Error
}

function readCache(domain: string): unknown {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + domain)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeCache(domain: string, payload: unknown): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + domain, JSON.stringify(payload))
  } catch {
    /* quota / private-mode — ignore, snapshot is still our floor */
  }
}

async function tryFetch(domain: string): Promise<unknown> {
  const response = await api.get(`/manifests/${domain}`)
  // Sanity-check the envelope before trusting the entries.
  ManifestMetaSchema.parse(response.data?.meta)
  assertSupportedVersion(domain, response.data.meta.manifest_version)
  return response.data
}

export async function fetchAlgorithmsManifest(): Promise<ManifestFetchResult<AlgorithmsManifest>> {
  try {
    const raw = await tryFetch('algorithms')
    const parsed = AlgorithmsManifestSchema.parse(raw)
    writeCache('algorithms', raw)
    return { data: parsed, source: 'live' }
  } catch (err) {
    const cached = readCache('algorithms')
    if (cached) {
      try {
        return {
          data: AlgorithmsManifestSchema.parse(cached),
          source: 'cache',
          error: err as Error,
        }
      } catch {
        /* fall through to snapshot */
      }
    }
    const fallbackSource = (snapshot as Record<string, unknown>).algorithms
    return {
      data: AlgorithmsManifestSchema.parse(fallbackSource),
      source: 'snapshot',
      error: err as Error,
    }
  }
}

/**
 * Test seam: re-export so unit tests can hand a fake `api` in via
 * module mocking, and assert on the cache path explicitly.
 */
export const _internal = {
  STORAGE_PREFIX,
  readCache,
  writeCache,
  ManifestVersionMismatchError,
}
