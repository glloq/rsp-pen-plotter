"""Base artifact type + deterministic hashing for the pipeline IR.

Every artifact carries:

- ``kind``   — discriminator (``source``, ``segmentation``, ``geometry``, ...)
- ``ir_version`` — schema version of the IR itself; bumped when the
  shape of any artifact changes in a way that affects hashing.
- ``hash``   — content-addressed SHA-256 over the canonicalized JSON
  payload + the IR version. Two artifacts with the same hash are
  guaranteed to be byte-identical, so a pipeline cache can short-circuit.

The hash is computed eagerly by ``artifact_hash(model)`` rather than
stored as a field; that keeps the wire format clean and makes it
impossible for the on-disk value to disagree with the computed one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# IR schema version. Bump (BREAKING) when the shape of any IR model
# changes in a way that would invalidate previously cached hashes. The
# value is folded into every hash so old and new caches can't collide.
IR_SCHEMA_VERSION = 1


class Artifact(BaseModel):
    """Base class for every IR artifact.

    Subclasses set ``kind`` to a stable literal (used by the hash and by
    consumers to dispatch). ``ir_version`` is captured on construction
    so an artifact can outlive an in-process schema bump (e.g. when read
    back from a persisted cache).
    """

    kind: str
    ir_version: int = Field(default=IR_SCHEMA_VERSION)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def hash_payload(self) -> dict[str, Any]:
        """Return the dict that goes into the content hash.

        ``created_at`` is excluded so logically-identical artifacts hash
        the same regardless of when they were produced. Subclasses can
        override to elide other ephemeral fields.
        """
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
        return payload


def artifact_hash(artifact: Artifact) -> str:
    """Compute the deterministic SHA-256 of ``artifact``'s canonical form.

    Two artifacts produce the same hash iff their :meth:`Artifact.hash_payload`
    serialize to byte-identical canonical JSON. The IR schema version is
    incorporated so a v1 cache cannot be misread as v2.
    """
    payload = {
        "ir_version": artifact.ir_version,
        "kind": artifact.kind,
        "data": artifact.hash_payload(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SourceAsset(Artifact):
    """The raw input bytes + their declared MIME, addressed by content hash.

    Fingerprints the upload so re-uploads of the same bytes share a cache
    entry. The bytes themselves are referenced by ``content_sha256``
    rather than embedded — actual storage lives in the file library.
    """

    kind: Literal["source"] = "source"
    filename: str
    mime: str
    size_bytes: int
    content_sha256: str


class MachineProgram(Artifact):
    """A compiled G-code stream ready to be sent to a machine.

    Carries the body plus enough metadata (profile name, dialect, line
    count) to identify the target machine without re-parsing.
    """

    kind: Literal["machine_program"] = "machine_program"
    profile_name: str
    dialect: str
    line_count: int
    gcode: str


class ExecutionRun(Artifact):
    """A bound program × machine × placement, with execution-time metadata.

    Not the run-time *state* (that lives in the queue / persistence
    layer); this artifact captures the immutable inputs of a run so
    historical executions can be re-keyed against the IR cache.
    """

    kind: Literal["execution_run"] = "execution_run"
    program_hash: str
    profile_name: str
    placement_hash: str | None = None
