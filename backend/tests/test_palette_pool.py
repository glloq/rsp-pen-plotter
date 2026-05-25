"""Tests for the palette-pool resolver — backend counterpart of the
frontend ``resolveEffectivePalette`` helper.

Pins the three-way branching (pens / available / union), the
case-insensitive dedup on union, and the ``active_pool`` shortcut
that reads the stored ``palette_source`` setting.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pen_plotter.api.available_colors import _normalise_hex
from pen_plotter.application.palette_pool import (
    active_pool,
    installed_pen_hexes,
    resolve_pool,
)
from pen_plotter.models import EbbConfig, MachineProfile, PenSlot, WorkspaceBounds
from pen_plotter.persistence import (
    AvailableColorRecord,
    delete_available_color,
    list_available_colors,
    save_available_color,
    set_setting,
)


def _profile(*pens: tuple[int, str, bool]) -> MachineProfile:
    """Build a minimal profile carrying the supplied (slot, hex, installed) pens."""
    slots = [
        PenSlot(index=slot, name=f"Pen {slot}", color=color, installed=installed)
        for slot, color, installed in pens
    ]
    return MachineProfile(
        name="test",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=100.0, y_max=100.0),
        origin="top_left",
        gcode_dialect="grbl",
        pen_up_command="",
        pen_down_command="",
        tool_change_method="manual_pause",
        tool_change_command="",
        drawing_speed_mm_s=30.0,
        travel_speed_mm_s=80.0,
        acceleration_mm_s2=500.0,
        pen_slot_count=max(1, len(pens)),
        ebb=EbbConfig(),
        pens=slots,
    )


@pytest.fixture(autouse=True)
def _reset_inventory_and_setting() -> None:
    """Clear the inventory + reset the setting between tests."""
    for record in list_available_colors():
        delete_available_color(record.color_id)
    set_setting("palette_source", "pens")
    yield


def _add_inventory(*hexes: str) -> None:
    """Insert one row per hex in document order (position 0, 1, …)."""
    for i, hex_value in enumerate(hexes):
        save_available_color(
            AvailableColorRecord(
                color_id=f"stub-{i}",
                hex=_normalise_hex(hex_value),
                name="",
                position=i,
                created_at=datetime.now(UTC),
            )
        )


def test_installed_pen_hexes_filters_out_uninstalled() -> None:
    """Only ``installed=True`` slots with a non-empty colour contribute."""
    profile = _profile(
        (0, "#ff0000", True),
        (1, "", True),  # blank colour drops out
        (2, "#0000ff", False),  # not installed drops out
        (3, "#00ff00", True),
    )
    assert installed_pen_hexes(profile) == ["#ff0000", "#00ff00"]


def test_installed_pen_hexes_returns_empty_for_none_profile() -> None:
    """No profile → empty list (caller routes to ``available`` / raw)."""
    assert installed_pen_hexes(None) == []


def test_resolve_pool_pens_returns_only_installed_pens() -> None:
    profile = _profile((0, "#111111", True), (1, "#222222", True))
    _add_inventory("#aaaaaa", "#bbbbbb")
    assert resolve_pool("pens", profile) == ["#111111", "#222222"]


def test_resolve_pool_available_returns_only_inventory() -> None:
    profile = _profile((0, "#111111", True))
    _add_inventory("#aaaaaa", "#bbbbbb")
    assert resolve_pool("available", profile) == ["#aaaaaa", "#bbbbbb"]


def test_resolve_pool_union_pens_first_inventory_extras_appended() -> None:
    profile = _profile((0, "#111111", True), (1, "#222222", True))
    _add_inventory("#aaaaaa", "#bbbbbb")
    assert resolve_pool("union", profile) == ["#111111", "#222222", "#aaaaaa", "#bbbbbb"]


def test_resolve_pool_union_dedups_inventory_against_pens() -> None:
    """Same hex on both sides → pens-side wins, inventory copy dropped."""
    profile = _profile((0, "#aaaaaa", True))
    _add_inventory("#aaaaaa", "#bbbbbb")
    assert resolve_pool("union", profile) == ["#aaaaaa", "#bbbbbb"]


def test_active_pool_honors_stored_palette_source_setting() -> None:
    """``active_pool`` reads ``palette_source`` and routes accordingly."""
    profile = _profile((0, "#111111", True))
    _add_inventory("#aaaaaa")
    set_setting("palette_source", "available")
    assert active_pool(profile) == ["#aaaaaa"]
    set_setting("palette_source", "union")
    assert active_pool(profile) == ["#111111", "#aaaaaa"]
    set_setting("palette_source", "pens")
    assert active_pool(profile) == ["#111111"]
