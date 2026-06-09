"""Drift test between the backend ``options_schema`` SoT and the
committed JSON snapshot the frontend reads from.

When this test fails, regenerate the snapshot:

    uv run python scripts/regen_algorithms_snapshot.py

The frontend has a matching test that compares ``ALGORITHMS`` in
``printRegistry.ts`` to the same file, so the two sides can't drift
without one of the tests catching it.
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


def _live_snapshot() -> list[dict[str, object]]:
    return [
        {
            "name": algo.name,
            "kind": algorithm_kind(algo.name),
            "complexity": algorithm_complexity(algo.name),
            "options": [opt.model_dump() for opt in algo.options_schema],
        }
        for algo in available_algorithms()
    ]


def test_options_snapshot_matches_backend() -> None:
    on_disk = json.loads(SNAPSHOT_PATH.read_text())
    live = _live_snapshot()
    assert on_disk == live, (
        "algorithmsSnapshot.json is stale — regenerate it with "
        "`uv run python scripts/regen_algorithms_snapshot.py`"
    )
