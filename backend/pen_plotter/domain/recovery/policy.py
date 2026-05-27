"""Recovery decision logic.

The mapping table from ``(RecoveryPolicy, FailureKind)`` to a concrete
:class:`Directive` is the contract — change it deliberately, with a
test, and update ``docs/profile_format.md`` if the user-visible
behaviour shifts.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from pen_plotter.domain.capability import RecoveryPolicy


class FailureKind(StrEnum):
    """Why the streamer reached a recovery decision."""

    SWAP_TIMEOUT = "swap_timeout"
    """The operator didn't confirm a manual swap within the timeout."""

    DEVICE_DISCONNECT = "device_disconnect"
    """The transport dropped (USB unplugged, serial reset, …)."""

    COMMAND_REJECTED = "command_rejected"
    """The firmware rejected a streamed line (error, alarm)."""

    OPERATOR_ABORT = "operator_abort"
    """The operator hit Stop/Abort in the UI."""

    UNKNOWN = "unknown"
    """Catch-all; treated as ``DEVICE_DISCONNECT`` for safety."""


class Directive(StrEnum):
    """What the queue/streamer should do next."""

    ABORT_RUN = "abort_run"
    """Mark the run failed; surface to the operator."""

    WAIT_FOR_OPERATOR = "wait_for_operator"
    """Pause indefinitely; the run resumes on operator confirm."""

    SKIP_AND_CONTINUE = "skip_and_continue"
    """Skip the failing layer/swap and continue with the next."""


class JobRecoveryOverride(BaseModel):
    """Per-job override of the profile's default recovery policy.

    Two fields rather than one so a job can override one transition
    without losing the others. ``None`` everywhere = fall back to the
    profile.
    """

    policy: RecoveryPolicy | None = None
    """Override the policy for *every* failure kind."""

    per_failure: dict[FailureKind, RecoveryPolicy] = Field(default_factory=dict)
    """Per-failure-kind override; takes precedence over ``policy``."""


class RecoveryDecision(BaseModel):
    """The resolved directive + audit trail."""

    directive: Directive
    effective_policy: RecoveryPolicy
    failure_kind: FailureKind
    reason: str = ""


# (policy, failure_kind) → directive mapping. ``OPERATOR_ABORT`` always
# aborts: an operator-initiated stop is never a candidate for "wait or
# skip". Everything else honours the policy.
_TABLE: dict[tuple[RecoveryPolicy, FailureKind], Directive] = {
    # ABORT — everything terminal except an already-fired operator abort.
    (RecoveryPolicy.ABORT, FailureKind.SWAP_TIMEOUT): Directive.ABORT_RUN,
    (RecoveryPolicy.ABORT, FailureKind.DEVICE_DISCONNECT): Directive.ABORT_RUN,
    (RecoveryPolicy.ABORT, FailureKind.COMMAND_REJECTED): Directive.ABORT_RUN,
    (RecoveryPolicy.ABORT, FailureKind.OPERATOR_ABORT): Directive.ABORT_RUN,
    (RecoveryPolicy.ABORT, FailureKind.UNKNOWN): Directive.ABORT_RUN,
    # PAUSE_AND_PROMPT — wait for the operator, except disconnect which
    # bypasses the policy and aborts (we can't trust the head's
    # position once the transport drops).
    (RecoveryPolicy.PAUSE_AND_PROMPT, FailureKind.SWAP_TIMEOUT): Directive.WAIT_FOR_OPERATOR,
    (RecoveryPolicy.PAUSE_AND_PROMPT, FailureKind.DEVICE_DISCONNECT): Directive.ABORT_RUN,
    (RecoveryPolicy.PAUSE_AND_PROMPT, FailureKind.COMMAND_REJECTED): Directive.WAIT_FOR_OPERATOR,
    (RecoveryPolicy.PAUSE_AND_PROMPT, FailureKind.OPERATOR_ABORT): Directive.ABORT_RUN,
    (RecoveryPolicy.PAUSE_AND_PROMPT, FailureKind.UNKNOWN): Directive.ABORT_RUN,
    # SKIP_LAYER — continue on swap/command failures; the run keeps
    # progressing but the offending layer is omitted. Disconnect and
    # operator abort are still terminal.
    (RecoveryPolicy.SKIP_LAYER, FailureKind.SWAP_TIMEOUT): Directive.SKIP_AND_CONTINUE,
    (RecoveryPolicy.SKIP_LAYER, FailureKind.DEVICE_DISCONNECT): Directive.ABORT_RUN,
    (RecoveryPolicy.SKIP_LAYER, FailureKind.COMMAND_REJECTED): Directive.SKIP_AND_CONTINUE,
    (RecoveryPolicy.SKIP_LAYER, FailureKind.OPERATOR_ABORT): Directive.ABORT_RUN,
    (RecoveryPolicy.SKIP_LAYER, FailureKind.UNKNOWN): Directive.ABORT_RUN,
}

_REASONS: dict[Directive, str] = {
    Directive.ABORT_RUN: "Failure not recoverable under the active policy.",
    Directive.WAIT_FOR_OPERATOR: "Failure recoverable — pausing for operator confirmation.",
    Directive.SKIP_AND_CONTINUE: "Failure recoverable — skipping and continuing the run.",
}


def effective_policy(
    profile_policy: RecoveryPolicy,
    job_override: JobRecoveryOverride | None,
    failure: FailureKind,
) -> RecoveryPolicy:
    """Pick the policy actually in effect for one failure event.

    Precedence: per-failure override > job-wide override > profile.
    """
    if job_override is not None:
        per_failure = job_override.per_failure.get(failure)
        if per_failure is not None:
            return per_failure
        if job_override.policy is not None:
            return job_override.policy
    return profile_policy


def resolve_recovery(
    profile_policy: RecoveryPolicy,
    job_override: JobRecoveryOverride | None,
    failure: FailureKind,
) -> RecoveryDecision:
    """Compute the :class:`Directive` for ``failure`` given the policy stack."""
    policy = effective_policy(profile_policy, job_override, failure)
    directive = _TABLE[(policy, failure)]
    return RecoveryDecision(
        directive=directive,
        effective_policy=policy,
        failure_kind=failure,
        reason=_REASONS[directive],
    )
