"""User-defined macro storage.

Macros are simple named sequences of raw plotter commands, persisted as a
single JSON document in a writable data file (``OMNIPLOT_MACROS_FILE``). The
file is keyed by macro name so saving a macro with an existing name overwrites
it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from pen_plotter.models import Macro

_log = logging.getLogger(__name__)

_DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "macros.json"
MACROS_FILE = Path(os.environ.get("OMNIPLOT_MACROS_FILE", _DEFAULT_FILE))


def _quarantine_corrupt(path: Path) -> None:
    """Move a corrupt macros file aside so the next save can't wipe it.

    Returning ``{}`` from a silently-swallowed JSON error means the next
    ``save_macro`` would rewrite the file with a single macro — losing
    every other one. Renaming the broken file preserves the operator's
    data for manual recovery and makes the failure loud in the logs.
    """
    backup = path.with_name(
        f"{path.name}.corrupt-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    )
    try:
        os.replace(path, backup)
    except OSError:
        _log.exception("Could not quarantine corrupt macros file %s", path)
        return
    _log.error(
        "Macros file %s is corrupt; moved it to %s. Starting from an empty "
        "macro set — recover the backup by hand if needed.",
        path,
        backup,
    )


def _read_all(path: Path = MACROS_FILE) -> dict[str, Macro]:
    """Load all macros keyed by name. A missing file → empty.

    A file that exists but does not parse is quarantined (renamed to a
    ``.corrupt-<timestamp>`` sibling, logged loudly) instead of being
    silently treated as empty — otherwise the very next save would
    overwrite the operator's whole macro library with one entry.
    """
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text())
    except OSError:
        _log.exception("Could not read macros file %s", path)
        return {}
    except json.JSONDecodeError:
        _quarantine_corrupt(path)
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
    """Atomically persist all macros, creating the directory if needed.

    tempfile + ``os.replace`` = atomic swap on POSIX (same pattern as
    ``presets._write_user_store``), so a crash mid-write leaves the
    previous good file in place rather than a truncated blob the next
    load would quarantine.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [macro.model_dump() for macro in macros.values()]
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
