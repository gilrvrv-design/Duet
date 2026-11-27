"""The serial link as a stream of lines: one JSON message per line, as the firmware's
serial port speaks it (``firmware/src/serial_link.h``).

A serial port reached over TCP (``tcp://host:port``) is how QEMU exposes the emulated
ESP32's UART, and how ser2net or esp_rfc2217_server expose a real one. Lines that are not
JSON (the boot log, the QEMU build's ``# strike ...`` reports) are not messages: they go
to ``console`` so tests and people can read them.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from urllib.parse import urlparse

CONSOLE_LINES = 2000  # console lines kept


class LineLink:
    """The same few methods the gateway uses on a WebSocket: send, recv, async for, close."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self.console: deque[str] = deque(maxlen=CONSOLE_LINES)

    @classmethod
    async def open(cls, url: str) -> LineLink:
        parts = urlparse(url)
        if parts.scheme != "tcp" or not parts.hostname or not parts.port:
            raise ValueError(f"expected tcp://host:port, got {url!r}")
        reader, writer = await asyncio.open_connection(parts.hostname, parts.port)
        return cls(reader, writer)

    async def send(self, text: str) -> None:
        self._writer.write(text.encode() + b"\n")
        await self._writer.drain()

    async def recv(self) -> str:
        """The next JSON message; other lines go to ``console``."""
        while True:
            raw = await self._reader.readline()
            if not raw:
                raise ConnectionError("serial link closed")
            line = raw.decode(errors="replace").strip()
            if line.startswith("{"):
                return line
            if line:
                self.console.append(line)

    def __aiter__(self) -> LineLink:
        return self

    async def __anext__(self) -> str:
        try:
            return await self.recv()
        except ConnectionError:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        self._writer.close()
        with contextlib.suppress(ConnectionError):
            await self._writer.wait_closed()
