"""Tests for the process-role boundary (roadmap D.6)."""

from __future__ import annotations

import pytest

from pen_plotter.deployment import (
    ProcessRole,
    capabilities_for,
    resolve_role,
)


def test_monolith_keeps_v0_1_capabilities() -> None:
    caps = capabilities_for(ProcessRole.MONOLITH)
    assert caps.serves_http is True
    assert caps.runs_queue_worker is True
    assert caps.owns_hardware_transport is True
    assert caps.ingests_telemetry is False


def test_api_serves_http_only() -> None:
    caps = capabilities_for(ProcessRole.API)
    assert caps.serves_http is True
    assert caps.runs_queue_worker is False
    assert caps.owns_hardware_transport is False


def test_render_owns_compute_no_http() -> None:
    caps = capabilities_for(ProcessRole.RENDER)
    assert caps.serves_http is False
    assert caps.runs_queue_worker is True
    assert caps.owns_hardware_transport is False


def test_executor_owns_hardware_only() -> None:
    caps = capabilities_for(ProcessRole.EXECUTOR)
    assert caps.serves_http is False
    assert caps.runs_queue_worker is False
    assert caps.owns_hardware_transport is True


def test_telemetry_ingests_only() -> None:
    caps = capabilities_for(ProcessRole.TELEMETRY)
    assert caps.serves_http is False
    assert caps.runs_queue_worker is False
    assert caps.owns_hardware_transport is False
    assert caps.ingests_telemetry is True


def test_resolve_defaults_to_monolith(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_ROLE", raising=False)
    assert resolve_role() is ProcessRole.MONOLITH


@pytest.mark.parametrize("role", list(ProcessRole))
def test_resolve_accepts_every_known_role(
    role: ProcessRole, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIPLOT_ROLE", role.value)
    assert resolve_role() is role


def test_resolve_falls_back_for_unknown_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OMNIPLOT_ROLE", "not-a-role")
    import logging

    caplog.set_level(logging.WARNING, logger="pen_plotter.deployment")
    role = resolve_role()
    assert role is ProcessRole.MONOLITH
    assert any(r.message == "unknown_process_role" for r in caplog.records)


def test_resolve_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_ROLE", "API")
    assert resolve_role() is ProcessRole.API
