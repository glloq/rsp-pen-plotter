"""Parameter presets for raster conversion.

Named bundles of converter options that give users sensible starting points
for common plotter-art styles. Ships with a fixed set of built-in presets;
operator-saved presets are persisted as JSON next to the SQLite DB so they
survive restarts without a schema migration.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_log = logging.getLogger(__name__)


class Preset(BaseModel):
    """A named bundle of converter options."""

    name: str
    description: str
    options: dict[str, Any]
    # ``"builtin"`` rows ship with the app and can't be overwritten or
    # deleted; ``"user"`` rows live in the JSON store and the operator
    # owns them.
    kind: str = "builtin"


BUILTIN_PRESETS: list[Preset] = [
    Preset(
        name="Fine line",
        description="Crisp two-color vector tracing for line art.",
        options={"algorithm": "direct", "num_colors": 2},
    ),
    Preset(
        name="Halftone",
        description="Variable-size dot screen, good for photographs.",
        options={
            "algorithm": "halftone",
            "num_colors": 3,
            "algorithm_options": {"cell_size_px": 6},
        },
    ),
    Preset(
        name="Stippling",
        description="Scattered dots that suggest tone through density.",
        options={
            "algorithm": "stippling",
            "num_colors": 2,
            "algorithm_options": {"density": 0.03},
        },
    ),
    Preset(
        name="Posterized",
        description="Direct tracing with more color separation.",
        options={"algorithm": "direct", "num_colors": 6},
    ),
]


_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "data" / "user_presets.json"
_STORE_PATH = Path(os.environ.get("OMNIPLOT_USER_PRESETS", _DEFAULT_STORE))


# Bounds the operator can't punch through. Names are echoed in URLs and
# UI labels; we keep them ASCII + space-ish to avoid surprises in either
# place. Descriptions and options stay free-form but length-capped so a
# stray paste can't bloat the JSON store unbounded.
_MAX_PRESETS = 64
_MAX_NAME_LEN = 64
_MAX_DESC_LEN = 256
_NAME_RE = re.compile(r"^[\w \-./()]{1,64}$")


def _read_user_store() -> list[Preset]:
    """Load the operator-saved presets, returning ``[]`` on first run / errors."""
    try:
        raw = _STORE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        _log.warning("user-presets store unreadable (%s); ignoring", exc)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("user-presets store corrupted (%s); ignoring", exc)
        return []
    if not isinstance(data, list):
        return []
    out: list[Preset] = []
    for entry in data:
        try:
            preset = Preset.model_validate(entry)
        except Exception:
            continue
        preset.kind = "user"
        out.append(preset)
    return out


def _write_user_store(presets: list[Preset]) -> None:
    """Atomically replace the operator-presets file."""
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [p.model_dump(mode="json") for p in presets]
    # tempfile + os.replace = atomic swap on POSIX so a crash mid-write
    # leaves the previous good file in place rather than a half-empty
    # blob the next load would discard.
    fd, tmp = tempfile.mkstemp(
        prefix=".user_presets.", suffix=".json", dir=str(_STORE_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        os.replace(tmp, _STORE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def list_presets() -> list[Preset]:
    """Return all available presets: built-ins first, then user-saved."""
    return [*BUILTIN_PRESETS, *_read_user_store()]


class PresetExistsError(ValueError):
    """Raised when an operator tries to overwrite a built-in preset."""


class PresetLimitError(ValueError):
    """Raised when the user-store would exceed ``_MAX_PRESETS``."""


class PresetNotFoundError(KeyError):
    """Raised when an operator tries to delete a preset that isn't there."""


def _normalize_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("preset name must not be empty")
    if len(stripped) > _MAX_NAME_LEN:
        raise ValueError(f"preset name must be ≤ {_MAX_NAME_LEN} chars")
    if not _NAME_RE.match(stripped):
        raise ValueError(
            "preset name may only contain letters, digits, spaces, and . - _ / ( )"
        )
    return stripped


def save_user_preset(name: str, description: str, options: dict[str, Any]) -> Preset:
    """Persist an operator-defined preset, replacing any same-name entry.

    Built-in names are reserved — calling this with a built-in name
    raises :class:`PresetExistsError`. Otherwise the new preset is
    appended (or its same-name predecessor replaced), and the file is
    atomically rewritten.
    """
    clean_name = _normalize_name(name)
    clean_desc = (description or "").strip()[:_MAX_DESC_LEN]
    if any(p.name == clean_name for p in BUILTIN_PRESETS):
        raise PresetExistsError(f"{clean_name!r} is a built-in preset name")
    if not isinstance(options, dict):
        raise ValueError("options must be a JSON object")

    presets = _read_user_store()
    presets = [p for p in presets if p.name != clean_name]
    if len(presets) >= _MAX_PRESETS:
        raise PresetLimitError(
            f"user preset limit reached ({_MAX_PRESETS}); delete one first"
        )
    new = Preset(
        name=clean_name,
        description=clean_desc,
        options=options,
        kind="user",
    )
    presets.append(new)
    _write_user_store(presets)
    return new


def delete_user_preset(name: str) -> None:
    """Remove an operator-defined preset by name."""
    presets = _read_user_store()
    if not any(p.name == name for p in presets):
        raise PresetNotFoundError(name)
    _write_user_store([p for p in presets if p.name != name])
