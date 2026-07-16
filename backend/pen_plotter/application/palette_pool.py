"""Resolve the active palette pool from the settings + profile + inventory.

The frontend's effective-palette helper has a Python mirror here so the
upload + rerender services can snap cluster centroids against the same
pool the operator sees in the editor. Keeping both implementations in
lock-step matters for two reasons:

- the snap result lands in the persisted ``assigned_color_hex`` so the
  hash + the G-code prompt agree with what the operator picked;
- the inventory store is the single source of truth — drifting between
  the UI's view and the backend's would surface as "I picked union but
  the prompt asks for a pen I uninstalled" bugs.

Resolution rule matches ``frontend/src/lib/effectivePalette.ts``:

- ``pens``      → installed pen hexes only
- ``available`` → available-colours inventory only
- ``union``     → pens first (machine reality wins on tie-break),
                  inventory extras appended, dedup is case-insensitive
"""

from __future__ import annotations

from pen_plotter.api.settings import PaletteSource, load_palette_source
from pen_plotter.models import MachineProfile
from pen_plotter.persistence import list_available_colors


def installed_pen_hexes(profile: MachineProfile | None) -> list[str]:
    """Return the lowercased hexes of currently-installed pen slots.

    Returns an empty list when no profile is selected or the profile
    has no ``pens`` DECLARED yet — callers route to ``available`` / the
    raw centroid in that case. Deliberately reads ``profile.pens``
    rather than ``effective_pens()``: the latter synthesizes one
    placeholder ``#000000`` installed slot per ``pen_slot_count`` for
    profiles that never configured their magazine, and those phantom
    black pens (a) snapped every dark cluster onto an ink the operator
    never declared and (b) diverged from the frontend pool, which reads
    ``profile.pens ?? []`` (see ``frontend/src/stores/job.ts``
    ``currentEffectivePalette``).
    """
    if profile is None:
        return []
    return [pen.color.lower() for pen in profile.pens or [] if pen.installed and pen.color]


def available_color_hexes() -> list[str]:
    """Return the lowercased hexes of the available-colours inventory, ordered."""
    return [record.hex.lower() for record in list_available_colors()]


def resolve_pool(
    source: PaletteSource,
    profile: MachineProfile | None,
) -> list[str]:
    """Compute the active palette pool given the source + profile.

    Args:
        source: The operator's choice (``pens`` / ``available`` / ``union``).
        profile: The active machine profile (needed for the pens branch).

    Returns:
        The ordered hex list the auto-attribution should snap against.
        ``pens`` first, then inventory extras for ``union``.
    """
    pens = installed_pen_hexes(profile)
    if source == "available":
        return available_color_hexes()
    if source == "union":
        inventory = available_color_hexes()
        seen = set(pens)
        extras = [h for h in inventory if h not in seen]
        return [*pens, *extras]
    return pens


def active_pool(profile: MachineProfile | None) -> list[str]:
    """Convenience helper: resolve the pool with the current global setting.

    Reads ``palette_source`` from ``AppSettingRecord``; the upload /
    rerender paths call this directly so they don't have to wire the
    setting through their own signatures.
    """
    return resolve_pool(load_palette_source(), profile)
