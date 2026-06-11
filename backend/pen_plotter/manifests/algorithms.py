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
  uses it to generate the form, A.7), derived from each algorithm's
  ``options_schema`` ClassVar
- ``recommended_presets`` — preset ids that work well with this algo
  (populated by phase B once the preset manifest lands)
"""

from __future__ import annotations

from typing import Any

from pen_plotter.converters.algorithms import (
    algorithm_complexity,
    algorithm_hidden,
    algorithm_kind,
    available_algorithms,
    get_algorithm,
)
from pen_plotter.manifests import Manifest, ManifestEntry, ManifestMeta, register_manifest

# Manifest schema version for this domain. Bump when the entry shape
# changes in a way that requires the frontend to upgrade.
# v3: ``hidden`` flag (duplicate consolidation) + the 2026-06 expert
# style batch (ridge_lines … penrose).
# v4: second style batch (dither … text_fill) + the ``text`` option
# type (free-form string knobs, e.g. text_fill's ``text``).
# v5: third batch (lsystem, chladni) + adaptive hilbert / radial
# ridge_lines options.
# v6: physical units — every length option formerly in raster pixels
# (``*_px``) is now declared in millimetres (``*_mm``), converted to
# raster pixels per placement at render time (``convert_mm_options``)
# so the on-paper pitch survives page-format changes. The ``*_px``
# spellings remain accepted on the wire for saved settings.
# v7: ``sine_halftone`` (tone-driven frequency-modulated waves — the
# sound-wave portrait).
ALGORITHMS_MANIFEST_VERSION = 7


class AlgorithmManifestEntry(ManifestEntry):
    """One algorithm's manifest payload."""

    name: str
    description: str = ""
    kind: str = "fill"
    complexity: str = "medium"
    # Hidden algorithms stay registered (persisted layers / presets keep
    # rendering) but the editor's pickers don't offer them for new
    # layers — each duplicates a visible entry (e.g. tsp → tsp_opt).
    hidden: bool = False
    params: dict[str, Any] = {}
    recommended_presets: list[str] = []


def _params_schema(algo_name: str) -> dict[str, Any]:
    """Return a JSON Schema fragment describing ``algo_name``'s knobs.

    Derived directly from the algorithm class's ``options_schema``
    ClassVar so backend and frontend can't drift. Algorithms with no
    schema (e.g. parameterless ``direct``) get an empty-properties
    object so the frontend still receives a well-formed schema.
    """
    algo = get_algorithm(algo_name)
    properties: dict[str, Any] = {}
    for opt in algo.options_schema:
        properties[opt.key] = opt.to_json_schema()
        properties[opt.key]["x-label"] = opt.label
    return {
        "type": "object",
        "properties": properties,
        # Permissive on extras: master styles inject internal hooks
        # (``angles``, ``intensity``, ``_tone``) that aren't operator-facing.
        "additionalProperties": True,
    }


def algorithms_manifest() -> Manifest[AlgorithmManifestEntry]:
    """Build the current algorithms manifest from the static registry."""
    entries = [
        AlgorithmManifestEntry(
            id=algo.name,
            name=algo.name,
            version=1,
            description=algo.description,
            kind=algorithm_kind(algo.name),
            complexity=algorithm_complexity(algo.name),
            hidden=algorithm_hidden(algo.name),
            params=_params_schema(algo.name),
        )
        for algo in available_algorithms()
    ]
    return Manifest[AlgorithmManifestEntry](
        meta=ManifestMeta(
            domain="algorithms",
            manifest_version=ALGORITHMS_MANIFEST_VERSION,
            schema_semver="0.2.0",
        ),
        entries=entries,
    )


def register() -> None:
    """Register the algorithms manifest provider with the global registry."""
    register_manifest("algorithms", algorithms_manifest)
