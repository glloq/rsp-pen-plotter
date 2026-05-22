"""Serial transport abstraction.

A :class:`Transport` is a minimal async line-oriented link to a controller.
:class:`SerialTransport` wraps ``pyserial-asyncio`` for real hardware;
:class:`MockTransport` emulates an ``ok``-acknowledging controller for tests
and offline development.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """A line-oriented, full-duplex link to a G-code controller."""

    async def write_line(self, line: str) -> None:
        """Send a single line (without trailing newline) to the controller."""
        ...

    async def read_line(self) -> str:
        """Read one response line from the controller, stripped of whitespace."""
        ...

    async def close(self) -> None:
        """Close the underlying connection."""
        ...


class MockTransport:
    """In-memory controller that replies ``ok`` to every command.

    Useful for testing the streamer and for offline development without
    hardware. Records every line written for assertions.
    """

    def __init__(self) -> None:
        """Create a mock transport with empty history."""
        self.written: list[str] = []
        self._responses: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False

    async def write_line(self, line: str) -> None:
        """Record the line and queue an ``ok`` acknowledgment."""
        self.written.append(line)
        await self._responses.put("ok")

    async def read_line(self) -> str:
        """Return the next queued response."""
        return await self._responses.get()

    async def close(self) -> None:
        """Mark the transport closed."""
        self.closed = True


class SerialTransport:
    """A :class:`Transport` backed by ``pyserial-asyncio``."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Wrap an open reader/writer pair.

        Args:
            reader: The serial stream reader.
            writer: The serial stream writer.
        """
        self._reader = reader
        self._writer = writer

    @classmethod
    async def open(cls, port: str, baudrate: int = 115200) -> SerialTransport:
        """Open a serial connection.

        Args:
            port: Serial device path, e.g. ``/dev/ttyUSB0``.
            baudrate: Connection baud rate.

        Returns:
            A connected :class:`SerialTransport`.
        """
        import serial_asyncio  # noqa: PLC0415  (optional hardware dependency)

        reader, writer = await serial_asyncio.open_serial_connection(url=port, baudrate=baudrate)
        return cls(reader, writer)

    async def write_line(self, line: str) -> None:
        """Write a line terminated with a newline and flush."""
        self._writer.write((line + "\n").encode("ascii"))
        await self._writer.drain()

    async def read_line(self) -> str:
        """Read one newline-terminated response and strip it."""
        data = await self._reader.readline()
        return data.decode("ascii", errors="replace").strip()

    async def close(self) -> None:
        """Close the serial writer."""
        self._writer.close()
