"""Tests for the auto-attribution helper that snaps cluster centroids to inks.

Covers the ΔE 2000 nearest-match resolution, the manual-override skip
behaviour, the empty-pool clear behaviour, the ``force`` flag for the
"reset all to auto" affordance, and the pool resolution rule used by
upload + generate to read the active inventory.
"""

from __future__ import annotations

from pen_plotter.application.color_assignment import (
    auto_assign_layer_colors,
    nearest_pool_hex,
)
from pen_plotter.models import BoundingBox, LayerInfo


def _layer(
    layer_id: str,
    source_color: str,
    *,
    assigned: str | None = None,
    color_assignment: str = "auto",
) -> LayerInfo:
    """Build a minimal LayerInfo for the assignment helpers."""
    return LayerInfo(
        layer_id=layer_id,
        source_color=source_color,
        target_pen_slot=None,
        draw_order=0,
        total_length_mm=10.0,
        path_count=1,
        bbox=BoundingBox(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0),
        assigned_color_hex=assigned,
        color_assignment=color_assignment,  # type: ignore[arg-type]
    )


def test_nearest_picks_perceptually_closest_in_lab() -> None:
    """A nearly-red centroid snaps to the red ink, not the green one.

    Sanity check that the ΔE 2000 path actually orders candidates by
    perceptual distance: ``#fa0202`` is much closer to red than to
    green even though RGB-euclidean would also pick red — this guards
    against a regression where the math degenerates to picking the
    first candidate.
    """
    result = nearest_pool_hex("#fa0202", ["#00ff00", "#ff0000", "#0000ff"])
    assert result is not None
    assert result.hex == "#ff0000"
    # ``#fa0202`` differs from ``#ff0000`` by ~2 ΔE — that's "just
    # noticeable" perceptually but well below the ~10 ΔE that would
    # indicate a wrong-bucket pick.
    assert result.delta_e < 5.0


def test_nearest_returns_none_for_empty_pool() -> None:
    """An empty pool surfaces as ``None`` so callers can skip cleanly."""
    assert nearest_pool_hex("#abcdef", []) is None


def test_nearest_canonicalises_hex_output() -> None:
    """Output is always the canonical ``#rrggbb`` form, even from shorthand."""
    result = nearest_pool_hex("#fff", ["#FFF", "#000"])
    assert result is not None
    assert result.hex == "#ffffff"


def test_auto_assign_snaps_each_layer_to_nearest_ink() -> None:
    """Every layer's centroid lands on its nearest pool hex with ``auto`` tag."""
    layers = [
        _layer("L1", "#ff0000"),
        _layer("L2", "#00ff00"),
        _layer("L3", "#1234ff"),
    ]
    pool = ["#fa0000", "#00fa00", "#0000fa"]
    result = auto_assign_layer_colors(layers, pool)
    assert [layer.assigned_color_hex for layer in result] == [
        "#fa0000",
        "#00fa00",
        "#0000fa",
    ]
    assert all(layer.color_assignment == "auto" for layer in result)


def test_auto_assign_skips_manual_overrides() -> None:
    """``color_assignment == "manual"`` rows are passed through unchanged."""
    layers = [
        _layer("L1", "#ff0000", assigned="#deadbe", color_assignment="manual"),
        _layer("L2", "#00ff00"),
    ]
    pool = ["#fa0000", "#00fa00"]
    result = auto_assign_layer_colors(layers, pool)
    # Manual row keeps its pinned hex; the auto row snaps.
    assert result[0].assigned_color_hex == "#deadbe"
    assert result[0].color_assignment == "manual"
    assert result[1].assigned_color_hex == "#00fa00"
    assert result[1].color_assignment == "auto"


def test_auto_assign_force_resnaps_manual_rows() -> None:
    """``force=True`` overrides the manual guard for the "reset all" affordance."""
    layers = [_layer("L1", "#ff0000", assigned="#deadbe", color_assignment="manual")]
    pool = ["#fa0000"]
    result = auto_assign_layer_colors(layers, pool, force=True)
    assert result[0].assigned_color_hex == "#fa0000"
    assert result[0].color_assignment == "auto"


def test_auto_assign_clears_when_pool_is_empty() -> None:
    """An empty pool drops stale auto assignments back to ``None``.

    Lets the G-code path cleanly fall back to ``source_color`` when the
    operator emptied the inventory + uninstalled every pen.
    """
    layers = [_layer("L1", "#ff0000", assigned="#fa0000")]
    result = auto_assign_layer_colors(layers, [])
    assert result[0].assigned_color_hex is None
    assert result[0].color_assignment == "auto"


def test_auto_assign_does_not_mutate_inputs() -> None:
    """The helper returns a fresh list; inputs survive untouched.

    Important because the upload path keeps a reference to
    ``converted.layers`` for diagnostics; surprise mutation there
    would corrupt the conversion result the caller relies on.
    """
    layers = [_layer("L1", "#ff0000")]
    pool = ["#fa0000"]
    auto_assign_layer_colors(layers, pool)
    assert layers[0].assigned_color_hex is None
    assert layers[0].color_assignment == "auto"
