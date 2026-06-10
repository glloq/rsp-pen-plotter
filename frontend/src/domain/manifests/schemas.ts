/**
 * Runtime validation schemas for the backend manifest envelope (roadmap A.7).
 *
 * Manifest payloads from `/manifests/{domain}` are parsed through these
 * zod schemas before any UI code touches them — a malformed or
 * version-mismatched payload surfaces as a typed error rather than a
 * runtime crash deep in a component.
 *
 * The shape mirrors `pen_plotter.manifests.base` on the backend (audit
 * #5 — single source of truth). Bumps to `manifest_version` are checked
 * by `assertSupportedVersion` so a frontend pinned to one schema
 * version refuses to misread a newer one.
 */
import { z } from 'zod'

export const DeprecationSchema = z.object({
  name: z.string(),
  reason: z.string().default(''),
  deprecated_since: z.number().int().nonnegative(),
  remove_after: z.number().int().nonnegative(),
})

export const ManifestMetaSchema = z.object({
  domain: z.string(),
  manifest_version: z.number().int().positive(),
  schema_semver: z.string().default('0.1.0'),
  generated_at: z.string(),
  deprecations: z.array(DeprecationSchema).default([]),
  feature_flags: z.record(z.string(), z.boolean()).default({}),
})

export const ManifestEntrySchema = z.object({
  id: z.string(),
  version: z.number().int().positive().default(1),
  deprecated: z.boolean().default(false),
})

export const AlgorithmManifestEntrySchema = ManifestEntrySchema.extend({
  name: z.string(),
  description: z.string().default(''),
  kind: z.enum(['fill', 'lines', 'mono_stroke']).default('fill'),
  complexity: z.enum(['low', 'medium', 'high']).default('medium'),
  // Hidden algorithms stay registered backend-side (persisted layers keep
  // rendering) but pickers must not offer them for new layers — each one
  // duplicates a visible entry (tsp → tsp_opt, grid → crosshatch, …).
  hidden: z.boolean().default(false),
  params: z.record(z.string(), z.unknown()).default({}),
  recommended_presets: z.array(z.string()).default([]),
})

export const AlgorithmsManifestSchema = z.object({
  meta: ManifestMetaSchema,
  entries: z.array(AlgorithmManifestEntrySchema),
})

export type ManifestMeta = z.infer<typeof ManifestMetaSchema>
export type Deprecation = z.infer<typeof DeprecationSchema>
export type AlgorithmManifestEntry = z.infer<typeof AlgorithmManifestEntrySchema>
export type AlgorithmsManifest = z.infer<typeof AlgorithmsManifestSchema>

/**
 * Highest `manifest_version` the frontend knows how to read for each
 * domain. Bumped together with the backend when the entry shape
 * changes in a way the UI needs to adapt to.
 */
export const SUPPORTED_MANIFEST_VERSION: Record<string, number> = {
  // v6: length options declared in millimetres (``*_mm``) instead of
  // raster pixels — see backend ``ALGORITHMS_MANIFEST_VERSION``.
  algorithms: 6,
  system: 1,
}

export class ManifestVersionMismatchError extends Error {
  constructor(
    public readonly domain: string,
    public readonly received: number,
    public readonly supported: number,
  ) {
    super(
      `manifest ${domain!} version ${received} not supported (this frontend supports up to ${supported})`,
    )
    this.name = 'ManifestVersionMismatchError'
  }
}

export function assertSupportedVersion(domain: string, received: number): void {
  const supported = SUPPORTED_MANIFEST_VERSION[domain]
  if (supported !== undefined && received > supported) {
    throw new ManifestVersionMismatchError(domain, received, supported)
  }
}

/**
 * Normalized API error envelope (roadmap A.4 backend counterpart).
 *
 * Every v0.2 endpoint emits this shape when it raises an `ApiError`.
 * The frontend dispatches on `code` (dot-namespaced, stable) rather
 * than parsing `message` strings.
 */
export const ApiErrorBodySchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.string(), z.unknown()).default({}),
  path: z.string().default(''),
})

export type ApiErrorBody = z.infer<typeof ApiErrorBodySchema>
