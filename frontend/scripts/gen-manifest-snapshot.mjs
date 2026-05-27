#!/usr/bin/env node
/**
 * Refresh src/domain/manifests/snapshot.json by calling the backend.
 *
 * Roadmap A.7. The snapshot is the offline floor of the manifest
 * client (`fetchAlgorithmsManifest` → 'snapshot' branch). Re-run this
 * after backend manifest changes so the build-time fallback stays
 * current. Equivalent to `npm run gen:manifests`.
 */
import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const backendRoot = resolve(here, '..', '..', 'backend')
const out = resolve(here, '..', 'src', 'domain', 'manifests', 'snapshot.json')

// `generated_at` is normalised to the epoch so the snapshot is
// deterministic — regenerating without backend changes produces a
// byte-identical file, which lets CI use a plain ``git diff`` as a
// drift gate. The live ``/manifests`` endpoint still emits the real
// generation time; only the bundled fallback gets the stable value.
const py = resolve(backendRoot, '.venv', 'bin', 'python')
const script = `
import json
from pen_plotter.manifests import get_manifest, available_domains
from pen_plotter.manifests_seed import register_default_manifests
register_default_manifests()

STABLE_GENERATED_AT = "1970-01-01T00:00:00+00:00"

def _normalise(payload):
    meta = payload.get("meta")
    if isinstance(meta, dict) and "generated_at" in meta:
        meta["generated_at"] = STABLE_GENERATED_AT
    return payload

out = {
    d: _normalise(get_manifest(d).model_dump(mode='json'))
    for d in available_domains()
}
print(json.dumps(out, indent=2))
`

const raw = execFileSync(py, ['-c', script], { cwd: backendRoot, encoding: 'utf8' })
writeFileSync(out, raw, 'utf8')
console.log(`snapshot updated: ${out} (${raw.length} bytes)`)
