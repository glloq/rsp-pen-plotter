"""Tests for the contract-drift CI check (roadmap D.5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def snapshot_path(tmp_path: Path) -> Path:
    return tmp_path / "snapshot.json"


def _write(snapshot_path: Path, payload: dict[str, object]) -> None:
    snapshot_path.write_text(json.dumps(payload))


def _import_check_contracts():
    # The script lives outside the package; import by path.
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_contracts.py"
    spec = importlib.util.spec_from_file_location("check_contracts", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_contracts"] = module
    spec.loader.exec_module(module)
    return module


def test_matching_snapshot_passes(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 1},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):

            class _M:
                def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                    return {
                        "meta": {"domain": "system", "manifest_version": 1},
                        "entries": [{"id": "version"}],
                    }

            with patch.object(cc, "get_manifest", return_value=_M()):
                rc = cc.check()
    assert rc == 0


def test_missing_snapshot_fails(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):
            rc = cc.check()
    assert rc == 1


def test_backend_ahead_of_snapshot_fails(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 1},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):

            class _M:
                def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                    return {
                        "meta": {"domain": "system", "manifest_version": 2},
                        "entries": [{"id": "version"}],
                    }

            with patch.object(cc, "get_manifest", return_value=_M()):
                rc = cc.check()
    assert rc == 1


def test_entry_drift_without_bump_fails(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 1},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):

            class _M:
                def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                    return {
                        "meta": {"domain": "system", "manifest_version": 1},
                        "entries": [{"id": "version"}, {"id": "new_entry"}],
                    }

            with patch.object(cc, "get_manifest", return_value=_M()):
                rc = cc.check()
    assert rc == 1


def test_snapshot_ahead_of_backend_fails(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 5},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):

            class _M:
                def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                    return {
                        "meta": {"domain": "system", "manifest_version": 1},
                        "entries": [{"id": "version"}],
                    }

            with patch.object(cc, "get_manifest", return_value=_M()):
                rc = cc.check()
    assert rc == 1


def _write_schemas_ts(path: Path, body: str) -> None:
    path.write_text(
        "export const SUPPORTED_MANIFEST_VERSION: Record<string, number> = {\n"
        f"{body}"
        "}\n"
    )


def test_frontend_cap_below_backend_fails(snapshot_path: Path, tmp_path: Path) -> None:
    # Backend + snapshot agree on v2, but the frontend ceiling stayed at
    # v1 — at runtime the UI would reject the live manifest and degrade
    # to its fallback. The check must catch the forgotten bump.
    cc = _import_check_contracts()
    schemas_ts = tmp_path / "schemas.ts"
    _write_schemas_ts(schemas_ts, "  system: 1,\n")
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 2},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "FRONTEND_SCHEMAS", schemas_ts):
            with patch.object(cc, "available_domains", return_value=["system"]):

                class _M:
                    def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                        return {
                            "meta": {"domain": "system", "manifest_version": 2},
                            "entries": [{"id": "version"}],
                        }

                with patch.object(cc, "get_manifest", return_value=_M()):
                    rc = cc.check()
    assert rc == 1


def test_frontend_cap_matching_backend_passes(snapshot_path: Path, tmp_path: Path) -> None:
    cc = _import_check_contracts()
    schemas_ts = tmp_path / "schemas.ts"
    # Comments inside the literal must not break the textual parse —
    # the real file documents every version bump inline.
    _write_schemas_ts(schemas_ts, "  // v2: bumped with the backend.\n  system: 2,\n")
    payload = {
        "system": {
            "meta": {"domain": "system", "manifest_version": 2},
            "entries": [{"id": "version"}],
        }
    }
    _write(snapshot_path, payload)
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "FRONTEND_SCHEMAS", schemas_ts):
            with patch.object(cc, "available_domains", return_value=["system"]):

                class _M:
                    def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                        return {
                            "meta": {"domain": "system", "manifest_version": 2},
                            "entries": [{"id": "version"}],
                        }

                with patch.object(cc, "get_manifest", return_value=_M()):
                    rc = cc.check()
    assert rc == 0


def test_real_frontend_ceiling_covers_backend_versions() -> None:
    # End-to-end guard on the actual repo files: every domain the real
    # frontend pins must support the version the real backend publishes.
    # This is the test that fails when someone bumps
    # ``ALGORITHMS_MANIFEST_VERSION`` without touching schemas.ts.
    cc = _import_check_contracts()
    from pen_plotter.manifests import available_domains, get_manifest
    from pen_plotter.manifests_seed import register_default_manifests

    register_default_manifests()
    supported = cc._frontend_supported_versions(cc.FRONTEND_SCHEMAS)
    assert supported, "SUPPORTED_MANIFEST_VERSION not found in frontend schemas.ts"
    for domain in available_domains():
        ceiling = supported.get(domain)
        if ceiling is None:
            continue
        backend_version = get_manifest(domain).meta.manifest_version
        assert backend_version <= ceiling, (
            f"{domain}: backend manifest_version={backend_version} exceeds the frontend "
            f"ceiling {ceiling} — bump SUPPORTED_MANIFEST_VERSION in schemas.ts"
        )


def test_domain_missing_from_snapshot_fails(snapshot_path: Path) -> None:
    cc = _import_check_contracts()
    _write(snapshot_path, {})  # empty snapshot
    with patch.object(cc, "SNAPSHOT", snapshot_path):
        with patch.object(cc, "available_domains", return_value=["system"]):

            class _M:
                def model_dump(self, mode: str = "json") -> dict[str, object]:  # noqa: ARG002
                    return {
                        "meta": {"domain": "system", "manifest_version": 1},
                        "entries": [],
                    }

            with patch.object(cc, "get_manifest", return_value=_M()):
                rc = cc.check()
    assert rc == 1
