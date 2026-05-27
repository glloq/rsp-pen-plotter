"""Generic manifest base types.

Concrete domains (algorithms, profiles, presets, ...) subclass
:class:`ManifestEntry` with their own payload fields and register a
:class:`Manifest` provider with :func:`register_manifest`. The frontend
sees the same envelope regardless of domain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class Deprecation(BaseModel):
    """One deprecated entry in a manifest.

    ``remove_after`` is the **first manifest version** that may legally
    omit the entry — frontends still pinned to an older version must
    keep supporting it until then.
    """

    name: str
    reason: str = ""
    deprecated_since: int
    remove_after: int


class ManifestMeta(BaseModel):
    """Envelope metadata shared by every manifest payload."""

    domain: str
    manifest_version: int = Field(ge=1)
    schema_semver: str = "0.1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deprecations: list[Deprecation] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class ManifestEntry(BaseModel):
    """Base class for entries in a manifest.

    Subclasses add a stable ``id`` plus domain-specific payload fields.
    """

    id: str
    version: int = 1
    deprecated: bool = False


EntryT = TypeVar("EntryT", bound=ManifestEntry)


class Manifest(BaseModel, Generic[EntryT]):  # noqa: UP046 — pydantic generics
    """A manifest = envelope + list of entries.

    Generic in the entry type so a domain provider can return a
    typed ``Manifest[AlgorithmManifestEntry]`` and FastAPI emits the
    proper OpenAPI schema.
    """

    meta: ManifestMeta
    entries: list[EntryT] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Materialize to a plain dict suitable for JSON snapshotting."""
        return self.model_dump(mode="json")
