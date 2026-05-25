"""Import-graph regression guard.

Locks in the L7 refactor: ``api/rerender`` and ``api/files`` must no
longer import from each other. The cycle used to be broken at runtime
by a lazy ``from pen_plotter.api.files import …`` inside
``_try_rehydrate``; this test pins the absence of the dependency at
the static-import level so a future "just add this import" doesn't
silently bring the cycle back.

The dependency direction this lot enforces is::

    api/rerender ──┐
                   ├──> application/file_library
    api/files ─────┘
"""

from __future__ import annotations

import ast
import pathlib

API_DIR = pathlib.Path(__file__).resolve().parent.parent / "pen_plotter" / "api"


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Return the set of fully-qualified module names imported by ``path``.

    Catches both ``import X`` and ``from X import Y``, at module level
    AND inside function bodies (so a sneaky lazy import is caught too).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                found.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
    return found


def test_rerender_does_not_import_files() -> None:
    imports = _imported_modules(API_DIR / "rerender.py")
    assert "pen_plotter.api.files" not in imports, (
        "api/rerender.py must not import api/files.py — "
        "go through application/file_library instead"
    )


def test_files_does_not_import_rerender() -> None:
    imports = _imported_modules(API_DIR / "files.py")
    assert "pen_plotter.api.rerender" not in imports, (
        "api/files.py must not import api/rerender.py — "
        "go through application/file_library instead"
    )
