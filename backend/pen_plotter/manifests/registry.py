"""Domain registry for manifest providers.

A domain provider is just a callable that returns the current
:class:`Manifest`. We deliberately keep this dead-simple: no plugin
discovery / entry points yet (audit #5 — additive first).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pen_plotter.manifests.base import Manifest

ManifestProvider = Callable[[], Manifest[Any]]


class UnknownManifestError(KeyError):
    """Raised when ``/manifests/{domain}`` is asked for an unregistered domain."""


_PROVIDERS: dict[str, ManifestProvider] = {}


def register_manifest(domain: str, provider: ManifestProvider) -> None:
    """Register (or replace) a provider for ``domain``."""
    _PROVIDERS[domain] = provider


def get_manifest(domain: str) -> Manifest[Any]:
    """Return the current manifest for ``domain``."""
    try:
        provider = _PROVIDERS[domain]
    except KeyError as exc:
        raise UnknownManifestError(domain) from exc
    return provider()


def available_domains() -> list[str]:
    """Return the registered domains, sorted for stable iteration."""
    return sorted(_PROVIDERS)
