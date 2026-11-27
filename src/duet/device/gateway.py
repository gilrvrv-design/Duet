"""The Hub side of the device link (spec §5.10).

``DeviceGateway`` is a blocking ``send(msg)`` device for the conductor. A background
thread runs the WebSocket. Timed commands are converted from Hub time to device time
using the measured clock offset.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import time

from websockets.asyncio.client import ClientConnection, connect

from duet.device.clock import ClockSync, SyncSample, best_sync, hub_now_us
from duet.protocol import TIMED, Ack, Hello, Message, TimePing, TimePong, parse_message


class DeviceGateway:
    def __init__(
        self,
        url: str,
        sync_samples: int = 16,
        timeout_s: float = 5.0,
        resync_every_s: float | None = 2.0,
    ) -> None:
        self.url = url
        self.sync_samples = sync_samples
        self.resync_every_s = resync_every_s
        self.timeout_s = timeout_s
        self.hello: Hello | None = None
        self.sync: ClockSync | None = None
        self.acked: set[int] = set()
        self.errors: list[str] = []
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._ws: ClientConnection | None = None
        self._reader_task: asyncio.Task | None = None
        self._resync_task: asyncio.Task | None = None
        self._sync_lock: asyncio.Lock | None = None
        self._pongs: asyncio.Queue[tuple[TimePong, int]] | None = None
        self._sent: set[int] = set()
        self._next_seq = 1_000_000  # gateway's own messages (pings) stay clear of plan seqs

    # lifecycle ---------------------------------------------------------------
    def connect(self) -> DeviceGateway:
        self._thread.start()
        self._call(self._connect())
        self.resync()
        if self.resync_every_s:
            self._resync_task = asyncio.run_coroutine_threadsafe(
                self._start_resync(), self._loop
            ).result(self.timeout_s)
        return self

    def close(self) -> None:
        if self._thread.is_alive():
            self._call(self._shutdown())
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=self.timeout_s)
        self._loop.close()

    async def _shutdown(self) -> None:
        for task in (self._resync_task, self._reader_task):
            if task is not None:
                task.cancel()
        if self._ws is not None:
            await self._ws.close()

    def __enter__(self) -> DeviceGateway:
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout_s)

    async def _connect(self) -> None:
        self._ws = await connect(self.url)
        self._pongs = asyncio.Queue()
        self._sync_lock = asyncio.Lock()
        first = parse_message(await self._ws.recv())
        if not isinstance(first, Hello):
            raise ConnectionError(f"device did not say hello: {first}")
        self.hello = first
        self._reader_task = self._loop.create_task(self._reader())

    async def _reader(self) -> None:
        async for text in self._ws:
            received = hub_now_us()
            msg = parse_message(text)
            if isinstance(msg, TimePong):
                await self._pongs.put((msg, received))
            elif isinstance(msg, Ack):
                if msg.status == "ok":
                    self.acked.add(msg.seq)
                else:
                    self.errors.append(f"seq {msg.seq}: {msg.status}")

    # clock sync --------------------------------------------------------------
    def resync(self) -> ClockSync:
        self.sync = self._call(self._sync())
        return self.sync

    async def _sync(self) -> ClockSync:
        async with self._sync_lock:  # one exchange at a time, so pongs match pings
            samples = []
            for _ in range(self.sync_samples):
                self._next_seq += 1
                await self._ws.send(TimePing(hub_now_us(), seq=self._next_seq).to_json())
                pong, t4 = await asyncio.wait_for(self._pongs.get(), self.timeout_s)
                samples.append(SyncSample(pong.t1, pong.t2, pong.t3, t4))
            return best_sync(samples, previous=self.sync)

    async def _start_resync(self) -> asyncio.Task:
        return asyncio.create_task(self._resync_forever())

    async def _resync_forever(self) -> None:
        """Keep the offset and drift fresh during long sessions (FR-D2)."""
        while True:
            await asyncio.sleep(self.resync_every_s)
            self.sync = await self._sync()

    # sending -----------------------------------------------------------------
    def send(self, msg: Message) -> None:
        if self.sync is None:
            raise RuntimeError("connect() before sending")
        if isinstance(msg, TIMED):
            msg = dataclasses.replace(msg, t_us=self.sync.to_device(msg.t_us))
        self._sent.add(msg.seq)
        self._call(self._ws.send(msg.to_json()))

    def wait_acked(self) -> None:
        """Block until the device acknowledged everything sent (FR-D4)."""
        deadline = time.monotonic() + self.timeout_s
        while not self._sent <= self.acked:
            if time.monotonic() > deadline:
                missing = sorted(self._sent - self.acked)[:5]
                raise TimeoutError(f"device did not acknowledge seq {missing}")
            time.sleep(0.005)
