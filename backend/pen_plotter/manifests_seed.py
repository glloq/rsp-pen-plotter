"""Default manifest providers registered at app startup.

The system manifest is the canonical, never-empty example so a frontend
calling ``/manifests`` always sees at least one domain. Concrete
domains (algorithms, profiles, presets, ...) land in roadmap step A.6
onwards.
"""

from __future__ import annotations

from typing import Any

from pen_plotter import __version__
from pen_plotter.manifests import Manifest, ManifestEntry, ManifestMeta, register_manifest


class SystemManifestEntry(ManifestEntry):
    """One system capability advertised to the frontend."""

    label: str = ""
    value: str = ""


def _system_manifest() -> Manifest[Any]:
    return Manifest[SystemManifestEntry](
        meta=ManifestMeta(
            domain="system",
            manifest_version=1,
            schema_semver="0.1.0",
            feature_flags={
                "ir_pipeline": False,
                "otel_tracing": False,
            },
        ),
        entries=[
            SystemManifestEntry(id="version", label="Backend version", value=__version__),
        ],
    )


def register_default_manifests() -> None:
    """Register the bundled manifest providers."""
    register_manifest("system", _system_manifest)
