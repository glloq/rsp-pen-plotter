"""Contract drift check (roadmap D.5).

Compares every backend manifest against the snapshot committed at
``frontend/src/domain/manifests/snapshot.json``. Two failure modes:

1. **Schema drift without version bump** — backend manifest_version
   equals the snapshot's, but the entry set differs. Forces a
   conscious bump.
2. **Stale snapshot** — backend manifest_version is **higher** than
   the snapshot's. Requires re-running ``npm run gen:manifests``.
3. **Stale frontend cap** — backend manifest_version is higher than
   the ``SUPPORTED_MANIFEST_VERSION`` ceiling declared in
   ``frontend/src/domain/manifests/schemas.ts``. Without the bump the
   frontend rejects the live manifest at runtime and silently degrades
   to its cache/snapshot fallback (the "manifest version N not
   supported" banner).

When the snapshot is **lower** (i.e. backend was bumped + snapshot
refreshed in the same PR), the check is happy — we're on the
deprecation window per ``docs/contract_architecture.md``.

Returns 0 on success, 1 on drift. Designed for CI; verbose enough
that the failure message tells the contributor what to do.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pen_plotter.manifests import available_domains, get_manifest
from pen_plotter.manifests_seed import register_default_manifests

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "frontend" / "src" / "domain" / "manifests" / "snapshot.json"
FRONTEND_SCHEMAS = REPO_ROOT / "frontend" / "src" / "domain" / "manifests" / "schemas.ts"


def _frontend_supported_versions(schemas_ts: Path) -> dict[str, int]:
    """Parse ``SUPPORTED_MANIFEST_VERSION`` out of the frontend schemas.

    Textual extraction (no TS tooling in this venv): grab the object
    literal that follows the constant name and collect its
    ``domain: N`` pairs. Comments inside the literal are fine — they
    never match the key/value pattern. Returns an empty dict when the
    file or the constant is missing so the caller can decide whether
    that is fatal.
    """
    if not schemas_ts.exists():
        return {}
    text = schemas_ts.read_text()
    match = re.search(
        r"SUPPORTED_MANIFEST_VERSION[^{]*\{(?P<body>[^}]*)\}",
        text,
        re.DOTALL,
    )
    if not match:
        return {}
    return {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"^\s*(\w+):\s*(\d+)", match.group("body"), re.MULTILINE)
    }


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
    frontend_supported = _frontend_supported_versions(FRONTEND_SCHEMAS)

    for domain in available_domains():
        backend = get_manifest(domain).model_dump(mode="json")
        b_ver = int(backend["meta"]["manifest_version"])
        # The frontend only pins domains it actively version-gates
        # (``assertSupportedVersion`` skips unknown domains), so a
        # missing key is fine — but a pinned ceiling below the backend
        # version means the live manifest gets rejected at runtime.
        supported = frontend_supported.get(domain)
        if supported is not None and b_ver > supported:
            schemas_location = (
                FRONTEND_SCHEMAS.relative_to(REPO_ROOT)
                if FRONTEND_SCHEMAS.is_relative_to(REPO_ROOT)
                else FRONTEND_SCHEMAS
            )
            failures.append(
                f"[{domain}] backend manifest_version={b_ver} > frontend "
                f"SUPPORTED_MANIFEST_VERSION={supported}; bump the ceiling in "
                f"{schemas_location} (and adapt the UI if the entry shape changed)."
            )
        snap = snapshot.get(domain)
        if not isinstance(snap, dict):
            failures.append(
                f"[{domain}] missing from snapshot — add to npm run gen:manifests output."
            )
            continue
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
