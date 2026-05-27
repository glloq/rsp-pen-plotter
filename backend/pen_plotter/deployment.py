"""Process-role configuration for multi-machine deployments (roadmap D.6).

Audit #1 §4 calls out the v0.1 "one process owns API + queue worker +
hardware control" coupling as a scaling ceiling. The v0.2 model
introduces explicit **process roles** so the same codebase can run as:

- a **monolith** (single process, today's default — appliance mode),
- an **API gateway** (HTTP only, delegates queue + execution),
- a **render worker** (no HTTP, picks up compute jobs),
- an **executor** (no HTTP, owns the hardware transport),
- a **telemetry collector** (no HTTP, sinks OTel + slo_breach events).

This module is the **contract**: it exposes which components each
role activates. The lifespan in :mod:`pen_plotter.main` honours the
role; deployments override via the ``OMNIPLOT_ROLE`` env var.

Today every role except ``monolith`` is **opt-in by configuration
only**: the components are loaded conditionally but the boundary is
in-process (no IPC yet). The next step (a separate PR per audit #1
phase 3) replaces the in-process calls with HTTP / queue messaging.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

_log = logging.getLogger(__name__)


class ProcessRole(StrEnum):
    """One of the five process roles."""

    MONOLITH = "monolith"
    """Default appliance mode — everything in one process."""

    API = "api"
    """HTTP gateway: routes only, no queue worker / hardware control."""

    RENDER = "render"
    """Compute worker: pulls jobs from the queue, no HTTP."""

    EXECUTOR = "executor"
    """Hardware controller: owns the transport, no HTTP."""

    TELEMETRY = "telemetry"
    """OTel collector / log sink, no HTTP."""


class RoleCapabilities:
    """Which subsystems the process activates for a role."""

    __slots__ = (
        "serves_http",
        "runs_queue_worker",
        "owns_hardware_transport",
        "ingests_telemetry",
    )

    def __init__(
        self,
        *,
        serves_http: bool,
        runs_queue_worker: bool,
        owns_hardware_transport: bool,
        ingests_telemetry: bool,
    ) -> None:
        """Bind the four capability flags."""
        self.serves_http = serves_http
        self.runs_queue_worker = runs_queue_worker
        self.owns_hardware_transport = owns_hardware_transport
        self.ingests_telemetry = ingests_telemetry


_CAPABILITIES: dict[ProcessRole, RoleCapabilities] = {
    ProcessRole.MONOLITH: RoleCapabilities(
        serves_http=True,
        runs_queue_worker=True,
        owns_hardware_transport=True,
        ingests_telemetry=False,
    ),
    ProcessRole.API: RoleCapabilities(
        serves_http=True,
        runs_queue_worker=False,
        owns_hardware_transport=False,
        ingests_telemetry=False,
    ),
    ProcessRole.RENDER: RoleCapabilities(
        serves_http=False,
        runs_queue_worker=True,
        owns_hardware_transport=False,
        ingests_telemetry=False,
    ),
    ProcessRole.EXECUTOR: RoleCapabilities(
        serves_http=False,
        runs_queue_worker=False,
        owns_hardware_transport=True,
        ingests_telemetry=False,
    ),
    ProcessRole.TELEMETRY: RoleCapabilities(
        serves_http=False,
        runs_queue_worker=False,
        owns_hardware_transport=False,
        ingests_telemetry=True,
    ),
}


def resolve_role() -> ProcessRole:
    """Resolve the active role from ``OMNIPLOT_ROLE``.

    Falls back to :class:`ProcessRole.MONOLITH` (the default appliance
    behaviour) on any unknown value, logging a warning so misconfigured
    deployments don't silently degrade.
    """
    raw = os.environ.get("OMNIPLOT_ROLE", "monolith").strip().lower()
    try:
        return ProcessRole(raw)
    except ValueError:
        _log.warning(
            "unknown_process_role",
            extra={"value": raw, "fallback": ProcessRole.MONOLITH.value},
        )
        return ProcessRole.MONOLITH


def capabilities_for(role: ProcessRole) -> RoleCapabilities:
    """Return the :class:`RoleCapabilities` table entry for ``role``."""
    return _CAPABILITIES[role]
