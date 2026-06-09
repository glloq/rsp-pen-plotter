"""Abstract raster algorithm interface.

A raster algorithm turns a single binary color region (a mask over the source
image) into plotter-friendly SVG geometry for one layer.

Each algorithm also declares an :data:`options_schema` describing its
operator-tunable knobs (bounds, defaults, label keys). This is the
single source of truth: the ``/algorithms`` endpoint, the manifest JSON
Schema, and the frontend form all derive from it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

OptionType = Literal["number", "integer", "boolean", "select"]


class OptionSpec(BaseModel):
    """One operator-tunable knob on a raster algorithm.

    ``key`` is the dict key the backend reads via ``options.get(key)``;
    ``label`` is an i18n key the frontend runs through ``t()``;
    ``default`` is the value used when the operator doesn't override it.

    ``min`` / ``max`` / ``step`` constrain number / integer inputs. For
    ``select`` knobs, ``choices`` is the list of allowed string values
    (the first one is the canonical default unless ``default`` says
    otherwise).
    """

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    type: OptionType
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Return a JSON Schema fragment describing this knob."""
        if self.type == "boolean":
            return {"type": "boolean", "default": self.default}
        if self.type == "select":
            return {
                "type": "string",
                "enum": list(self.choices or []),
                "default": self.default,
            }
        # number / integer share the numeric envelope; ``integer`` adds
        # the integer constraint so callers (zod, ajv) reject decimals.
        schema: dict[str, Any] = {
            "type": "integer" if self.type == "integer" else "number",
            "default": self.default,
        }
        if self.min is not None:
            schema["minimum"] = self.min
        if self.max is not None:
            schema["maximum"] = self.max
        if self.step is not None:
            schema["multipleOf"] = self.step
        return schema


class RasterAlgorithm(ABC):
    """Renders one binary color region into an SVG layer group."""

    name: ClassVar[str]
    description: ClassVar[str]
    # Per-algorithm operator knobs. Default empty so legacy algorithms
    # without exposed options (or pre-schema ones during a partial
    # migration) keep working — they just won't appear in the form.
    options_schema: ClassVar[list[OptionSpec]] = []
    # True when the algorithm reads the per-pixel luminance map the
    # render pipeline injects as ``options["_tone"]`` (0=black..1=white).
    # The pipeline only pays the dict-copy for algorithms that opt in.
    tone_aware: ClassVar[bool] = False

    @abstractmethod
    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render a color region as an SVG ``<g>`` group.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex color for the layer, e.g. ``"#1a2b3c"``.
            label: Human-readable layer label.
            options: Optional algorithm-specific parameters.

        Returns:
            A single SVG ``<g>...</g>`` group as a string. Coordinates are in
            pixel space matching the source image (origin top-left).
        """
        raise NotImplementedError
