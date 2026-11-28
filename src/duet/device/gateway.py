"""The Hub side of the device link (spec §5.10).

``DeviceGateway`` is a blocking ``send(msg)`` device for the conductor. A background
thread runs the link: a WebSocket (``ws://``, the rig over Wi-Fi) or a serial port
reached over TCP (``tcp://``, e.g. the firmware in QEMU; see ``duet.device.lines``).
Timed commands are converted from Hub time to device time using the measured clock
offset.

Every message gets a wire ``seq`` of the gateway's own, so two performances that both
number their plan from 1 can never confuse acknowledgements. Anything that means the
performance cannot go on (a lost connection, an error ack, a fatal fault) wakes every
waiter and is raised as ``DeviceFault`` from the next ``send`` or wait.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
import time
from collections.abc import Callable

from websockets.asyncio.client import ClientConnection, connect

from duet.device.clock import ClockSync, SyncSample, best_sync, hub_now_us
from duet.device.limits import DeviceLimits, mismatches
from duet.device.lines import LineLink
from duet.profile import RobotProfile
from duet.protocol import (
    CARRIAGE_STRIKER,
    PROTOCOL,
    TIMED,
    Ack,
    Channel,
    Fault,
    Heartbeat,
    Hello,
    Home,
    Message,
    Play,
    Song,
    Stop,
    Telemetry,
    TimePing,
    TimePong,
    parse_message,
)

log = logging.getLogger(__name__)

# Faults after which the rig cannot carry on without a person (docs/device-protocol.md).
FATAL_FAULTS = frozenset({"WATCHDOG", "HOMING_TIMEOUT"})
SYNC_SAMPLES = 16
HEARTBEAT_EVERY_S = 0.25  # a quarter of the firmware's 1 s watchdog
RESYNC_EVERY_S = 2.0


class DeviceFault(RuntimeError):
    """The device refused something, faulted, or the connection was lost."""


class DeviceMismatch(ConnectionError):
    """The device enforces different limits than the profile the Hub plans with."""


class DeviceGateway:
    def __init__(
        self,
        url: str,
        sync_samples: int = SYNC_SAMPLES,
        timeout_s: float = 5.0,
        resync_every_s: float | None = RESYNC_EVERY_S,
        heartbeat_every_s: float = HEARTBEAT_EVERY_S,
        profile: RobotProfile | None = None,
        now_us: Callable[[], int] = hub_now_us,
    ) -> None:
        self.url = url
        self.sync_samples = sync_samples
        self.resync_every_s = resync_every_s
        self.heartbeat_every_s = heartbeat_every_s
        self.timeout_s = timeout_s
        self.profile = profile
        self.now_us = now_us
        self.hello: Hello | None = None
        self.channels: dict[str, int] = {}  # kind -> channel number, from the greeting
        self.limits: DeviceLimits | None = None  # its carriage's, if it has one
        self.sync: ClockSync | None = None
        self.errors: list[str] = []
        self.faults: list[Fault] = []
        self.telemetry: Telemetry | None = None
        self._state = threading.Condition()  # guards everything below; notified on change
        self._homed = False
        self._failure: str | None = None
        self._unacked: dict[int, int] = {}  # wire seq -> the caller's seq
        self._wire_seq = 0
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._ws: ClientConnection | LineLink | None = None
        self._tasks: list[asyncio.Task] = []
        self._sync_lock: asyncio.Lock | None = None
        self._pongs: asyncio.Queue[tuple[TimePong, int]] | None = None

    # lifecycle ---------------------------------------------------------------
    def connect(self) -> DeviceGateway:
        self._thread.start()
        try:
            self._call(self._connect())
            self.resync()
        except BaseException:
            self.close()
            raise
        if self.resync_every_s:
            self._start(self._resync_forever(), "resync")
        self._start(self._heartbeat_forever(), "heartbeat")
        return self

    def close(self) -> None:
        if self._thread.is_alive():
            self._call(self._shutdown())
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=self.timeout_s)
        if not self._loop.is_closed():
            self._loop.close()

    async def _shutdown(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._ws is not None:
            await self._ws.close()

    def __enter__(self) -> DeviceGateway:
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self.timeout_s)

    def _start(self, coro, name: str) -> None:
        def create() -> None:
            task = self._loop.create_task(coro, name=name)
            task.add_done_callback(self._task_done)
            self._tasks.append(task)

        self._loop.call_soon_threadsafe(create)

    def _task_done(self, task: asyncio.Task) -> None:
        """A background task must never die silently: its death stops the performance."""
        if task.cancelled():
            return
        exc = task.exception()
        reason = f"{task.get_name()} stopped: {exc!r}" if exc else "connection closed"
        if exc:
            log.error("device link %s", reason)
        self._fail(reason)

    def _fail(self, reason: str) -> None:
        with self._state:
            if self._failure is None:
                self._failure = reason
            self._state.notify_all()

    async def _connect(self) -> None:
        if self.url.startswith("tcp://"):
            self._ws = await LineLink.open(self.url)  # a serial port over TCP (e.g. QEMU)
        else:
            self._ws = await connect(self.url)
        self._pongs = asyncio.Queue()
        self._sync_lock = asyncio.Lock()
        self.hello = await self._expect(Hello)
        if self.hello.protocol != PROTOCOL:
            raise ConnectionError(
                f"device {self.hello.device_id} speaks protocol {self.hello.protocol}; "
                f"this Hub speaks {PROTOCOL}: update one of them"
            )
        described = [await self._expect(Channel) for _ in range(self.hello.channels)]
        self.channels = {c.kind: c.ch for c in described}  # kind -> channel number
        carriages = [c for c in described if c.kind == CARRIAGE_STRIKER]
        self.limits = DeviceLimits.from_channel(carriages[0]) if carriages else None
        self._check_profile()
        task = self._loop.create_task(self._reader(), name="reader")
        task.add_done_callback(self._task_done)
        self._tasks.append(task)

    async def _expect(self, kind: type[Message]) -> Message:
        """The next message of the greeting, which must be ``kind``."""
        msg = parse_message(await self._ws.recv())
        if not isinstance(msg, kind):
            raise ConnectionError(f"device greeting: expected {kind.type}, got {msg}")
        return msg

    def _check_profile(self) -> None:
        if self.profile is None:
            return
        problems = []
        if self.hello.profile != self.profile.id:
            problems.append(f"profile: device {self.hello.profile}, Hub {self.profile.id}")
        if self.limits is None:
            problems.append("the device has no carriage to play this robot")
        else:
            problems += mismatches(self.limits, self.profile)
        if problems:
            raise DeviceMismatch("device and profile disagree: " + "; ".join(problems))

    async def _reader(self) -> None:
        async for text in self._ws:
            received = self.now_us()
            msg = parse_message(text)
            if isinstance(msg, TimePong):
                await self._pongs.put((msg, received))
            else:
                self._receive(msg)

    def _receive(self, msg: Message) -> None:
        with self._state:
            if isinstance(msg, Telemetry):
                self.telemetry = msg
                self._homed = msg.homed
            elif isinstance(msg, Fault):
                self.faults.append(msg)
                if msg.code in FATAL_FAULTS:
                    self._homed = False
                    self._failure = self._failure or f"fault {msg.code}: {msg.detail}"
            elif isinstance(msg, Ack):
                seq = self._unacked.pop(msg.seq, msg.seq)
                if msg.status != "ok":
                    self.errors.append(f"seq {seq}: {msg.status}")
                    self._failure = self._failure or f"device refused seq {seq}: {msg.status}"
            self._state.notify_all()

    def _check(self) -> None:
        """Raise if the performance cannot go on. Call with ``_state`` held."""
        if self._failure is not None:
            raise DeviceFault(self._failure)

    @property
    def console(self) -> list[str]:
        """Non-message lines from a serial link (boot log, QEMU hardware reports)."""
        return list(self._ws.console) if isinstance(self._ws, LineLink) else []

    # clock sync --------------------------------------------------------------
    def resync(self) -> ClockSync:
        self.sync = self._call(self._sync())
        return self.sync

    def _next_wire_seq(self) -> int:
        with self._state:
            self._wire_seq += 1
            return self._wire_seq

    async def _sync(self) -> ClockSync:
        async with self._sync_lock:  # one exchange at a time, so pongs match pings
            samples = []
            for _ in range(self.sync_samples):
                ping = TimePing(self.now_us(), seq=self._next_wire_seq())
                await self._ws.send(ping.to_json())
                pong, t4 = await asyncio.wait_for(self._pongs.get(), self.timeout_s)
                samples.append(SyncSample(pong.t1, pong.t2, pong.t3, t4))
            return best_sync(samples, previous=self.sync)

    async def _resync_forever(self) -> None:
        """Keep the offset and drift fresh during long sessions (FR-D2)."""
        while True:
            await asyncio.sleep(self.resync_every_s)
            self.sync = await self._sync()

    async def _heartbeat_forever(self) -> None:
        """Never let the device go a whole watchdog period without hearing from us."""
        beat = Heartbeat().to_json()
        while True:
            await self._ws.send(beat)
            await asyncio.sleep(self.heartbeat_every_s)

    # sending -----------------------------------------------------------------
    def send(self, msg: Message) -> None:
        if self.sync is None:
            raise RuntimeError("connect() before sending")
        if isinstance(msg, TIMED):
            msg = dataclasses.replace(msg, t_us=self.sync.to_device(msg.t_us))
        wire = self._next_wire_seq()
        with self._state:
            self._check()
            if isinstance(msg, Home):
                self._homed = False
            self._unacked[wire] = msg.seq
        self._call(self._ws.send(dataclasses.replace(msg, seq=wire).to_json()))

    # songs stored on the device ---------------------------------------------
    def upload(self, slot: int, commands: list[Message]) -> None:
        """Store a compiled song (duet.songs) in a slot on the device. Its times are
        song times, not Hub times, so it bypasses send(): no clock conversion."""
        wire = self._next_wire_seq()
        with self._state:
            self._check()
            self._unacked[wire] = wire
        lines = [Song(slot=slot, lines=len(commands), seq=wire).to_json()]
        lines += [m.to_json() for m in commands]
        self._call(self._send_lines(lines))
        self.wait_acked()

    async def _send_lines(self, lines: list[str]) -> None:
        for line in lines:
            await self._ws.send(line)

    def play(self, slot: int) -> None:
        """Play a stored song: the device homes, then plays it on its own."""
        self.send(Play(slot=slot))
        self.wait_acked()

    def stop(self) -> None:
        self.send(Stop())
        self.wait_acked()

    def _wait(self, done: Callable[[], bool], timeout_s: float, what: str) -> None:
        deadline = time.monotonic() + timeout_s
        with self._state:
            while not done():
                self._check()
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(what)
                self._state.wait(left)
            self._check()

    def wait_ready(self, timeout_s: float) -> Telemetry:
        """Block until the device reports it is homed."""
        self._wait(lambda: self._homed, timeout_s, "device did not report homed")
        return self.telemetry

    def wait_acked(self) -> None:
        """Block until the device acknowledged everything sent (FR-D4)."""

        def what() -> str:
            return f"device did not acknowledge seq {sorted(self._unacked.values())[:5]}"

        try:
            self._wait(lambda: not self._unacked, self.timeout_s, "")
        except TimeoutError:
            raise TimeoutError(what()) from None
