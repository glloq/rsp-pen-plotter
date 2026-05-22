"""Parameter presets for raster conversion.

Named bundles of converter options that give users sensible starting points
for common plotter-art styles.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Preset(BaseModel):
    """A named bundle of converter options."""

    name: str
    description: str
    options: dict[str, Any]


PRESETS: list[Preset] = [
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


def list_presets() -> list[Preset]:
    """Return all available presets."""
    return PRESETS
