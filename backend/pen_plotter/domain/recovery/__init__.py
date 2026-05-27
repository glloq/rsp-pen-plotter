"""Recovery decision layer (roadmap B.3 / audit #2).

Audit #2 splits *what to do when a swap fails* into a per-profile
default policy and an optional per-job override (decision frozen
2026-05-27). This module is the **pure, testable decision layer**:

    resolve_recovery(profile_policy, job_override, failure) -> Directive

Consumers (queue, streamer, UI) call into here to turn a
``RecoveryPolicy`` value + a concrete :class:`FailureKind` into a
:class:`Directive` they can act on. Nothing about the persisted queue
shape changes — the existing pause/resume mechanism stays in
:mod:`pen_plotter.queue`; this layer just makes the policy explicit
and machine-readable.
"""

from __future__ import annotations

from pen_plotter.domain.recovery.policy import (
    Directive,
    FailureKind,
    JobRecoveryOverride,
    RecoveryDecision,
    effective_policy,
    resolve_recovery,
)

__all__ = [
    "Directive",
    "FailureKind",
    "JobRecoveryOverride",
    "RecoveryDecision",
    "effective_policy",
    "resolve_recovery",
]
