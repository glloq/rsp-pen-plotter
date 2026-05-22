"""MIME-keyed registry mapping input formats to converters."""

from __future__ import annotations

from pen_plotter.converters.base import Converter, UnsupportedFormatError


class ConverterRegistry:
    """Indexes converter instances by the MIME types they support."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_mime: dict[str, Converter] = {}

    def register(self, converter: Converter) -> None:
        """Register a converter for each of its supported MIME types.

        Args:
            converter: The converter instance to register.

        Raises:
            ValueError: If a MIME type is already claimed by another converter,
                or if the converter declares no supported MIME types.
        """
        if not converter.supported_mimes:
            raise ValueError(f"{type(converter).__name__} declares no supported MIME types")
        for mime in converter.supported_mimes:
            if mime in self._by_mime:
                raise ValueError(f"MIME type {mime!r} is already registered")
            self._by_mime[mime] = converter

    def for_mime(self, mime: str) -> Converter:
        """Return the converter registered for a MIME type.

        Args:
            mime: The MIME type to look up.

        Returns:
            The converter that handles the given MIME type.

        Raises:
            UnsupportedFormatError: If no converter is registered for the type.
        """
        converter = self._by_mime.get(mime)
        if converter is None:
            raise UnsupportedFormatError(mime)
        return converter

    def supported_mimes(self) -> set[str]:
        """Return the set of all currently registered MIME types."""
        return set(self._by_mime)


registry = ConverterRegistry()
