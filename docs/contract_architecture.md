# Contract architecture

Source-of-truth strategy for the data contracts shared between the
backend and the frontend, introduced by roadmap step **A.4** and
extended through step **A.7**.

## Goals

1. The backend is the **single source of truth** for every model the UI
   consumes (algorithm metadata, machine profiles, presets, plans, …).
2. The frontend never duplicates defaults or parameter bounds — it
   reads them from a manifest.
3. Contracts evolve **additive-first** with explicit version bumps and
   a deprecation window long enough that an older frontend keeps
   working against a newer backend.

## Two layers

### 1. API shapes — OpenAPI

Static request/response types (uploads, jobs, runs, queue, …) are
described by FastAPI's auto-generated OpenAPI schema. The frontend
runs `openapi-typescript` against it to produce strict TypeScript
types.

Generate the schema with::

    cd backend && .venv/bin/python scripts/generate_openapi.py > ../frontend/openapi.json

### 2. Dynamic metadata — manifests

Anything **the UI needs to enumerate** (available algorithms with
their parameter bounds, presets, machine profiles, …) is exposed as a
manifest at ``/manifests/{domain}``. Each manifest carries an envelope
with version metadata so the frontend knows whether it can read it.

### Envelope shape

```json
{
  "meta": {
    "domain": "system",
    "manifest_version": 1,
    "schema_semver": "0.1.0",
    "generated_at": "2026-05-27T22:11:00Z",
    "deprecations": [
      {"name": "old_thing", "reason": "...", "deprecated_since": 1, "remove_after": 4}
    ],
    "feature_flags": {"beta_x": true}
  },
  "entries": [
    {"id": "alpha", "version": 1, "deprecated": false, "label": "Alpha"}
  ]
}
```

- **`manifest_version`** is an integer that **monotonically increases**
  on every schema change. Parsers MUST refuse a version they don't
  understand. SemVer (`schema_semver`) is informational only.
- **`deprecations`** is the contract for sunsetting entries: each
  entry must remain in the manifest until at least
  ``max(2 manifest versions, 2 months)`` after ``deprecated_since``,
  with the exact removal version captured in ``remove_after``.
- **`feature_flags`** are domain-scoped flags the frontend toggles UI
  on (e.g. ``ir_pipeline``).

## Adding a new domain

1. Subclass :class:`pen_plotter.manifests.ManifestEntry` with the
   domain-specific fields (id, params, bounds, …).
2. Write a provider function that returns
   ``Manifest[YourEntry](meta=..., entries=[...])``.
3. Register it from ``pen_plotter.manifests_seed.register_default_manifests``
   (or from a domain-specific init module called there).
4. The endpoint ``/manifests/{your_domain}`` is wired automatically.

## Errors

Manifest endpoints — and every v0.2 endpoint going forward — emit
normalized errors via :class:`pen_plotter.errors.ApiError`::

    {
      "code": "manifest.unknown_domain",
      "message": "no manifest registered for domain 'bogus'",
      "details": {"requested": "bogus", "available": ["system"]},
      "path": "/manifests/bogus"
    }

Codes are dot-namespaced (``domain.specific_failure``) so the frontend
can dispatch user-facing messages on ``code`` rather than parsing
``message`` strings.

## Frontend consumption (preview — lands with A.7)

- Snapshot of every served manifest is bundled at build time as the
  **offline fallback**.
- On boot the frontend calls each ``/manifests/{domain}`` it cares
  about, validates the payload with a zod schema, and caches the
  result in ``localStorage`` so the next reload survives a backend
  outage.
- A small banner notifies the operator when the UI is serving from
  fallback rather than live data.

## Versioning policy summary

| Change                                  | Action                                  |
|-----------------------------------------|------------------------------------------|
| New field on an entry                   | additive — no version bump required      |
| New required field                      | bump ``manifest_version``; old field stays optional during window |
| New entry                               | additive                                 |
| Removing an entry                       | mark deprecated first, wait window, then remove + bump version |
| Renaming a field                        | add new + deprecate old, bump version when old is removed |

A CI guard (roadmap step **D.5**) diffs the served manifest against
the committed snapshots and blocks merges that change the schema
without bumping ``manifest_version``.
