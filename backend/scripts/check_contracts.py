"""Contract drift check (roadmap D.5).

Compares every backend manifest against the snapshot committed at
``frontend/src/domain/manifests/snapshot.json``. Two failure modes:

1. **Schema drift without version bump** — backend manifest_version
   equals the snapshot's, but the entry set differs. Forces a
   conscious bump.
2. **Stale snapshot** — backend manifest_version is **higher** than
   the snapshot's. Requires re-running ``npm run gen:manifests``.

When the snapshot is **lower** (i.e. backend was bumped + snapshot
refreshed in the same PR), the check is happy — we're on the
deprecation window per ``docs/contract_architecture.md``.

Returns 0 on success, 1 on drift. Designed for CI; verbose enough
that the failure message tells the contributor what to do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pen_plotter.manifests import available_domains, get_manifest
from pen_plotter.manifests_seed import register_default_manifests

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "frontend" / "src" / "domain" / "manifests" / "snapshot.json"


def _entries_signature(payload: dict[str, object]) -> set[str]:
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return set()
    sigs: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            sigs.add(str(entry.get("id", "")))
    return sigs


def check() -> int:
    """Run the contract check; return process exit code."""
    register_default_manifests()

    if not SNAPSHOT.exists():
        print(f"FAIL: snapshot missing at {SNAPSHOT}", file=sys.stderr)
        print(
            "Run `npm run gen:manifests` from frontend/ to create it.",
            file=sys.stderr,
        )
        return 1

    snapshot = json.loads(SNAPSHOT.read_text())
    if not isinstance(snapshot, dict):
        print("FAIL: snapshot is not a JSON object", file=sys.stderr)
        return 1

    failures: list[str] = []

    for domain in available_domains():
        backend = get_manifest(domain).model_dump(mode="json")
        snap = snapshot.get(domain)
        if not isinstance(snap, dict):
            failures.append(
                f"[{domain}] missing from snapshot — add to npm run gen:manifests output."
            )
            continue
        b_ver = int(backend["meta"]["manifest_version"])
        s_ver = int(snap["meta"]["manifest_version"])
        if b_ver < s_ver:
            failures.append(
                f"[{domain}] backend manifest_version={b_ver} is older than snapshot={s_ver}; "
                "did you forget to merge a backend bump?"
            )
            continue
        if b_ver > s_ver:
            failures.append(
                f"[{domain}] backend manifest_version={b_ver} > snapshot={s_ver}; "
                "run `npm run gen:manifests` to refresh the snapshot in this PR."
            )
            continue
        # Same version → entries must match.
        b_sig = _entries_signature(backend)
        s_sig = _entries_signature(snap)
        if b_sig != s_sig:
            added = sorted(b_sig - s_sig)
            removed = sorted(s_sig - b_sig)
            failures.append(
                f"[{domain}] entry set changed without a version bump.\n"
                f"   added:   {added}\n"
                f"   removed: {removed}\n"
                "   Bump manifest_version OR revert the change."
            )

    if failures:
        print("CONTRACT DRIFT DETECTED:", file=sys.stderr)
        for line in failures:
            print(f" - {line}", file=sys.stderr)
        return 1

    print(f"contracts OK ({len(available_domains())} domains, snapshot at {SNAPSHOT})")
    return 0


if __name__ == "__main__":
    sys.exit(check())
