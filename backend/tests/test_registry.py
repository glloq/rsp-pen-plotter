import pytest

from pen_plotter.converters.base import Converter, UnsupportedFormatError
from pen_plotter.converters.registry import ConverterRegistry
from pen_plotter.converters.svg import SvgConverter


def test_register_and_lookup_by_mime() -> None:
    reg = ConverterRegistry()
    reg.register(SvgConverter())
    assert isinstance(reg.for_mime("image/svg+xml"), SvgConverter)
    assert reg.supported_mimes() == {"image/svg+xml"}


def test_lookup_unknown_mime_raises() -> None:
    reg = ConverterRegistry()
    with pytest.raises(UnsupportedFormatError):
        reg.for_mime("application/pdf")


def test_duplicate_registration_raises() -> None:
    reg = ConverterRegistry()
    reg.register(SvgConverter())
    with pytest.raises(ValueError):
        reg.register(SvgConverter())


def test_converter_without_mimes_raises() -> None:
    class Empty(Converter):
        def convert(self, data: bytes, *, options: dict | None = None):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    reg = ConverterRegistry()
    with pytest.raises(ValueError):
        reg.register(Empty())


def test_svg_passthrough_preserves_markup() -> None:
    result = SvgConverter().convert(b"<svg>hi</svg>")
    assert result.svg == "<svg>hi</svg>"
    assert result.source_mime == "image/svg+xml"
