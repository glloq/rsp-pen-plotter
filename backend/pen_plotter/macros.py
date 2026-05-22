"""User-defined macro storage.

Macros are simple named sequences of raw plotter commands, persisted as a
single JSON document in a writable data file (``OMNIPLOT_MACROS_FILE``). The
file is keyed by macro name so saving a macro with an existing name overwrites
it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from pen_plotter.models import Macro

_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "macros.json"
MACROS_FILE = Path(os.environ.get("OMNIPLOT_MACROS_FILE", _DEFAULT_FILE))


def _read_all(path: Path = MACROS_FILE) -> dict[str, Macro]:
    """Load all macros keyed by name. Missing or invalid file → empty."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    macros: dict[str, Macro] = {}
    for item in raw if isinstance(raw, list) else []:
        try:
            macro = Macro.model_validate(item)
        except ValidationError:
            continue
        macros[macro.name] = macro
    return macros


def _write_all(macros: dict[str, Macro], path: Path = MACROS_FILE) -> None:
    """Persist all macros to the JSON file, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [macro.model_dump() for macro in macros.values()]
    path.write_text(json.dumps(payload, indent=2))


def load_macros(path: Path = MACROS_FILE) -> list[Macro]:
    """Return all macros sorted by name."""
    return sorted(_read_all(path).values(), key=lambda macro: macro.name)


def get_macro(name: str, path: Path = MACROS_FILE) -> Macro | None:
    """Return the macro with the given name, or ``None``."""
    return _read_all(path).get(name)


def save_macro(macro: Macro, path: Path = MACROS_FILE) -> Macro:
    """Create or update a macro by name."""
    macros = _read_all(path)
    macros[macro.name] = macro
    _write_all(macros, path)
    return macro


def delete_macro(name: str, path: Path = MACROS_FILE) -> bool:
    """Delete a macro by name. Returns ``True`` if one was removed."""
    macros = _read_all(path)
    if name not in macros:
        return False
    del macros[name]
    _write_all(macros, path)
    return True
