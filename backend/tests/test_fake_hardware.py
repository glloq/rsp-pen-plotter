"""``OMNIPLOT_FAKE_HARDWARE=1`` swaps the real serial transport for a mock (P7).

Lets Playwright drive the connect → queue → plot loop without a real
plotter on the test runner.
"""

from __future__ import annotations

import pytest

from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.transport import MockTransport, SerialTransport


@pytest.mark.asyncio
async def test_open_serial_attaches_mock_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_FAKE_HARDWARE", "1")
    controller = PlotterController()
    # Port path is bogus on purpose: the mock branch must not touch the OS.
    await controller.open_serial("/dev/does-not-exist", baudrate=115200)
    assert controller.connected
    # The attached transport must be the in-memory mock, not a real serial.
    assert isinstance(controller._transport, MockTransport)
    await controller.disconnect()


@pytest.mark.asyncio
async def test_open_serial_uses_real_transport_when_flag_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNIPLOT_FAKE_HARDWARE", raising=False)
    controller = PlotterController()
    # Without the flag, the call should try the real path; we don't
    # actually want to open a serial port in CI, so monkeypatch
    # ``SerialTransport.open`` to a sentinel and assert it's the chosen
    # code branch.
    sentinel_calls: list[tuple[str, int, str]] = []

    async def fake_open(port: str, baudrate: int, terminator: str) -> SerialTransport:
        sentinel_calls.append((port, baudrate, terminator))
        # Return a MockTransport disguised as a SerialTransport so the
        # controller's ``attach`` accepts it.
        return MockTransport()  # type: ignore[return-value]

    monkeypatch.setattr(SerialTransport, "open", fake_open)
    await controller.open_serial("/dev/ttyUSB0", baudrate=9600, terminator="\r")
    assert sentinel_calls == [("/dev/ttyUSB0", 9600, "\r")]
    await controller.disconnect()


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_flag_recognises_common_truthy_values(
    monkeypatch: pytest.MonkeyPatch, truthy: str
) -> None:
    from pen_plotter.hardware.controller import _fake_hardware_enabled

    monkeypatch.setenv("OMNIPLOT_FAKE_HARDWARE", truthy)
    assert _fake_hardware_enabled() is True


@pytest.mark.parametrize("falsy", ["", "0", "false", "no", "off"])
def test_flag_recognises_common_falsy_values(
    monkeypatch: pytest.MonkeyPatch, falsy: str
) -> None:
    from pen_plotter.hardware.controller import _fake_hardware_enabled

    monkeypatch.setenv("OMNIPLOT_FAKE_HARDWARE", falsy)
    assert _fake_hardware_enabled() is False
