"""Algorithm manifest provider (roadmap A.6).

Replaces the v0.1 ``/algorithms`` endpoint as **the** wire format the
frontend consumes for algorithm metadata. The legacy endpoint stays in
place for now (it still serves the same data) but the canonical
description — including parameter bounds, defaults and recommended
presets — is the manifest at ``/manifests/algorithms``.

Each entry carries:

- ``id`` / ``version`` — stable identity + per-algorithm version
- ``kind`` / ``complexity`` — UI grouping + static cost class
- ``description`` — operator-facing text
- ``params`` — JSON Schema fragment describing the tunables (frontend
  uses it to generate the form, A.7)
- ``recommended_presets`` — preset ids that work well with this algo
  (populated by phase B once the preset manifest lands)
"""

from __future__ import annotations

from typing import Any

from pen_plotter.converters.algorithms import (
    algorithm_complexity,
    algorithm_kind,
    available_algorithms,
)
from pen_plotter.manifests import Manifest, ManifestEntry, ManifestMeta, register_manifest

# Manifest schema version for this domain. Bump when the entry shape
# changes in a way that requires the frontend to upgrade.
ALGORITHMS_MANIFEST_VERSION = 1


class AlgorithmManifestEntry(ManifestEntry):
    """One algorithm's manifest payload."""

    name: str
    description: str = ""
    kind: str = "fill"
    complexity: str = "medium"
    params: dict[str, Any] = {}
    recommended_presets: list[str] = []


def _default_params_schema(algo_name: str) -> dict[str, Any]:
    """Return a minimal JSON Schema fragment for ``algo_name``.

    Each algorithm currently exposes only an ``options`` dict whose
    contents are validated by the converter on the way in. The schema
    captured here is intentionally **permissive** for now — the v0.2
    resolver work (phase B) will pin tight bounds with calibrated
    defaults per algorithm, and that's what the frontend zod schema
    (A.7) will key on.
    """
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }


def algorithms_manifest() -> Manifest[AlgorithmManifestEntry]:
    """Build the current algorithms manifest from the static registry.

    A pure function of the registry — easy to call from tests, easy to
    snapshot for the frontend offline fallback. Phase B will replace
    the registry call with a dynamic plugin discovery layer; the
    manifest shape stays the same.
    """
    entries = [
        AlgorithmManifestEntry(
            id=algo.name,
            name=algo.name,
            version=1,
            description=algo.description,
            kind=algorithm_kind(algo.name),
            complexity=algorithm_complexity(algo.name),
            params=_default_params_schema(algo.name),
        )
        for algo in available_algorithms()
    ]
    return Manifest[AlgorithmManifestEntry](
        meta=ManifestMeta(
            domain="algorithms",
            manifest_version=ALGORITHMS_MANIFEST_VERSION,
            schema_semver="0.1.0",
        ),
        entries=entries,
    )


def register() -> None:
    """Register the algorithms manifest provider with the global registry."""
    register_manifest("algorithms", algorithms_manifest)
