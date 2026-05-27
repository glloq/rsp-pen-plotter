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

    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_contracts.py"
    )
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
