"""Versioned plugin manifests (roadmap A.4).

A manifest is the **source of truth** for one domain (algorithms,
profiles, presets, plans, ...). The backend serves manifests at
``/manifests/{domain}`` and the frontend consumes them dynamically via
zod schemas (roadmap A.7). Defaults, parameter bounds, and recommended
presets live in manifests rather than being hardcoded in both layers.

Each manifest carries:

- ``manifest_version: int`` — bumped on every schema change. **The
  parser uses this** to decide whether it can read the payload.
- ``schema_semver`` — informational SemVer string for changelogs.
- ``generated_at`` — UTC timestamp when the response was produced.
- ``deprecations`` — list of names that consumers should stop using;
  each entry carries ``deprecated_since`` and ``remove_after``.
- ``feature_flags`` — flags relevant to consumers of this domain.

Deprecation policy: a name marked deprecated stays in the manifest for
**max(2 manifest versions, 2 months)** so frontends shipped against an
older version keep working. See ``docs/contract_architecture.md``.
"""

from __future__ import annotations

from pen_plotter.manifests.base import (
    Deprecation,
    Manifest,
    ManifestEntry,
    ManifestMeta,
)
from pen_plotter.manifests.registry import (
    UnknownManifestError,
    available_domains,
    get_manifest,
    register_manifest,
)

__all__ = [
    "Deprecation",
    "Manifest",
    "ManifestEntry",
    "ManifestMeta",
    "UnknownManifestError",
    "available_domains",
    "get_manifest",
    "register_manifest",
]
