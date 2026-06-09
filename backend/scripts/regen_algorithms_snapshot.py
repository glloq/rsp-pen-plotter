"""Regenerate ``frontend/src/data/algorithmsSnapshot.json``.

The snapshot is the contract test fixture between the backend's
``options_schema`` (single source of truth) and the frontend's hand-
maintained ``ALGORITHMS`` map in ``printRegistry.ts``. Two tests pin it:

- ``backend/tests/test_algorithms_options_snapshot.py`` — backend matches
  the committed snapshot
- ``frontend/src/data/algorithmsSnapshot.test.ts`` — frontend registry
  matches the committed snapshot

Run this script after touching any algorithm's ``options_schema`` ClassVar.

Usage::

    uv run python scripts/regen_algorithms_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pen_plotter.converters.algorithms import (
    algorithm_complexity,
    algorithm_kind,
    available_algorithms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "frontend" / "src" / "data" / "algorithmsSnapshot.json"


def build_snapshot() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for algo in available_algorithms():
        out.append(
            {
                "name": algo.name,
                "kind": algorithm_kind(algo.name),
                "complexity": algorithm_complexity(algo.name),
                "options": [opt.model_dump() for opt in algo.options_schema],
            }
        )
    return out


def main() -> None:
    snapshot = build_snapshot()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"wrote {SNAPSHOT_PATH} ({len(snapshot)} algorithms)")


if __name__ == "__main__":
    main()
