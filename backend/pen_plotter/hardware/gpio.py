"""Raspberry Pi GPIO control for the camera-station light (ADR 0005).

The offset-calibration light is wired to a Pi GPIO pin (a relay or an LED
driver), so the *host* drives it — not the plotter. This module is a thin,
injectable wrapper that resolves a real GPIO backend lazily (so a non-Pi dev
box or CI imports cleanly) and exposes a single ``set(pin, on)`` operation.

Backends are tried in order: ``lgpio`` (modern Pi OS), then ``RPi.GPIO``
(legacy). When neither imports, :attr:`LightController.available` is ``False``
and :meth:`set` raises — callers surface that to the operator instead of
silently pretending the light switched.
"""

from __future__ import annotations

import threading
from typing import Protocol

# BCM GPIO pins broken out on the Pi 40-pin header (excluding the power/ground
# pins and the reserved ID-EEPROM pins 0/1). Operators pick one to drive the
# light; this is the list the UI offers.
AVAILABLE_GPIO_PINS: tuple[int, ...] = (
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
)


class GpioBackend(Protocol):
    """Minimal GPIO output backend: drive ``pin`` to a boolean level."""

    def set(self, pin: int, value: bool) -> None: ...


class _LgpioBackend:
    """``lgpio`` backend (Raspberry Pi OS bookworm+)."""

    def __init__(self, lgpio: object) -> None:
        self._lg = lgpio
        self._chip = lgpio.gpiochip_open(0)  # type: ignore[attr-defined]
        self._claimed: set[int] = set()

    def set(self, pin: int, value: bool) -> None:
        if pin not in self._claimed:
            self._lg.gpio_claim_output(self._chip, pin)  # type: ignore[attr-defined]
            self._claimed.add(pin)
        self._lg.gpio_write(self._chip, pin, 1 if value else 0)  # type: ignore[attr-defined]


class _RpiGpioBackend:
    """Legacy ``RPi.GPIO`` backend."""

    def __init__(self, gpio: object) -> None:
        self._gpio = gpio
        gpio.setmode(gpio.BCM)  # type: ignore[attr-defined]
        gpio.setwarnings(False)  # type: ignore[attr-defined]
        self._claimed: set[int] = set()

    def set(self, pin: int, value: bool) -> None:
        if pin not in self._claimed:
            self._gpio.setup(pin, self._gpio.OUT)  # type: ignore[attr-defined]
            self._claimed.add(pin)
        self._gpio.output(pin, bool(value))  # type: ignore[attr-defined]


def _resolve_backend() -> GpioBackend | None:
    """Return a real GPIO backend, or ``None`` when not on a Pi / no library."""
    try:
        import lgpio  # type: ignore

        return _LgpioBackend(lgpio)
    except Exception:  # not a Pi, lib missing, or no /dev/gpiochip0
        pass
    try:
        import RPi.GPIO as GPIO  # type: ignore

        return _RpiGpioBackend(GPIO)
    except Exception:
        pass
    return None


_UNSET = object()


class LightController:
    """Drives a GPIO-connected light. Thread-safe; backend resolved lazily."""

    def __init__(self, backend: object = _UNSET) -> None:
        # ``_UNSET`` → resolve the real backend now; an explicit value (incl.
        # ``None``) is honoured so tests inject a fake or force "unavailable".
        self._backend: GpioBackend | None = (
            _resolve_backend() if backend is _UNSET else backend  # type: ignore[assignment]
        )
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """Whether a real GPIO backend was found on this host."""
        return self._backend is not None

    def set(self, pin: int, on: bool, active_high: bool = True) -> None:
        """Switch the light on/off on ``pin`` (BCM).

        Raises:
            RuntimeError: If no GPIO backend is available on this host.
        """
        if self._backend is None:
            raise RuntimeError("GPIO is not available on this host.")
        level = on if active_high else not on
        with self._lock:
            self._backend.set(pin, level)


# One controller per appliance.
light = LightController()
