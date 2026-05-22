"""Abstract converter interface and shared conversion types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class UnsupportedFormatError(Exception):
    """Raised when no registered converter handles a given MIME type."""

    def __init__(self, mime: str) -> None:
        """Store the offending MIME type and build a readable message.

        Args:
            mime: The MIME type that no converter could handle.
        """
        self.mime = mime
        super().__init__(f"No converter registered for MIME type: {mime!r}")


class ConversionResult(BaseModel):
    """Outcome of normalizing an input to the SVG pivot format."""

    svg: str
    source_mime: str
    warnings: list[str] = Field(default_factory=list)


class Converter(ABC):
    """Base class for all format converters.

    Subclasses declare the MIME types they handle via ``supported_mimes`` and
    implement :meth:`convert`, which turns raw input bytes into normalized SVG.
    """

    supported_mimes: ClassVar[frozenset[str]] = frozenset()

    @abstractmethod
    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Normalize raw input bytes to the SVG pivot format.

        Args:
            data: The raw bytes of the input file.
            options: Optional converter-specific parameters.

        Returns:
            The normalized SVG wrapped in a :class:`ConversionResult`.
        """
        raise NotImplementedError
