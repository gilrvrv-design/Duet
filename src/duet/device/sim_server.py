"""A simulated rig device on a real WebSocket (spec §9.1 digital twin).

It behaves like the ESP32 will: it answers clock pings with its own clock, acknowledges
every command, queues timed commands and runs them against the physics simulator.
Its clock is offset from the Hub on purpose, so clock sync is really exercised.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from websockets.asyncio.server import ServerConnection, serve

from duet.device.clock import hub_now_us
from duet.device.limits import DeviceLimits
from duet.device.lines import LineLink
from duet.profile import RobotProfile, robot_profile
from duet.protocol import (
    CARRIAGE_STRIKER,
    LED_STRIP,
    MIDI_OUT,
    PROTOCOL,
    TIMED,
    Ack,
    Channel,
    Estop,
    Fault,
    Greet,
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
from duet.sim import RIG_CHANNELS, RIG_LEDS, SimulatedRig

log = logging.getLogger(__name__)


@dataclass
class SimulatedDevice:
    profile: RobotProfile = field(default_factory=robot_profile)
    clock_offset_us: int = 987_654_321
    drift_ppm: float = 0.0  # a real crystal is off by tens of ppm
    device_id: str = "sim-1"
    protocol: int = PROTOCOL  # another value plays a device on an older firmware
    rig: SimulatedRig = field(init=False)
    commands: int = 0
    heartbeats: int = 0
    homing_s: float = 0.0  # how long the simulated carriage takes to find home
    homed_at_us: int | None = None  # device time homing finished
    early_commands: int = 0  # timed commands scheduled before homing finished
    homing_fails: bool = False  # the home sensor never triggers
    estopped: bool = False  # latched, like the firmware: only a power cycle clears it

    def __post_init__(self) -> None:
        self.rig = SimulatedRig(self.profile)
        self._start = hub_now_us()

    def now_us(self) -> int:
        return round(self.true_device_time(hub_now_us()))

    def true_device_time(self, hub_us: int) -> float:
        """The device clock at a Hub time: what sync tries to learn."""
        return hub_us + self.clock_offset_us + self.drift_ppm * (hub_us - self._start) / 1e6

    def handle(self, msg: Message) -> list[tuple[float, Message]]:
        """Replies to one message, each with a delay in seconds."""
        if isinstance(msg, TimePing):
            arrived = self.now_us()
            return [(0.0, TimePong(msg.t1, arrived, self.now_us(), seq=msg.seq))]
        if isinstance(msg, Heartbeat):
            self.heartbeats += 1
            return []
        if isinstance(msg, Greet):  # as the firmware: the greeting again, no ack
            return [(0.0, m) for m in self.greeting()]
        if isinstance(msg, Stop):  # as the firmware (protocol 5): what is queued is dropped
            self.rig.received.clear()
            return [(0.0, Ack(seq=msg.seq))]
        if isinstance(msg, Song | Play):
            # Play from memory lives in the firmware; the full-loop tests cover it
            # (tests/test_firmware_loop.py). This simulator only streams live.
            return [(0.0, Ack(seq=msg.seq, status="error: not supported by the simulator"))]
        if isinstance(msg, Estop):
            self.estopped = True
        elif self.estopped:
            return [(0.0, Ack(seq=msg.seq, status="error: emergency stop"))]
        if isinstance(msg, Home):
            self.homed_at_us = self.now_us() + round(self.homing_s * 1_000_000)
        elif isinstance(msg, TIMED) and (self.homed_at_us is None or msg.t_us < self.homed_at_us):
            self.early_commands += 1
        self.rig.send(msg)
        self.commands += 1
        replies = [(0.0, Ack(seq=msg.seq))]
        if isinstance(msg, Home) and self.homing_fails:
            replies.append(
                (self.homing_s, Fault(code="HOMING_TIMEOUT", detail="home sensor never triggered"))
            )
        elif isinstance(msg, Home):
            replies.append((self.homing_s, Telemetry(homed=True, position=0)))
        return replies

    def greeting(self) -> list[Message]:
        """What the firmware sends on connect (Device::greet): hello, then its channels,
        the rig's: the carriage, the LED strip, MIDI out."""
        hello = Hello(
            protocol=self.protocol,
            device_id=self.device_id,
            board="sim",
            profile=self.profile.id,
            channels=len(RIG_CHANNELS),
        )
        carriage = DeviceLimits.from_profile(self.profile).to_channel(
            RIG_CHANNELS[CARRIAGE_STRIKER]
        )
        strip = Channel(ch=RIG_CHANNELS[LED_STRIP], kind=LED_STRIP, count=RIG_LEDS)
        midi = Channel(ch=RIG_CHANNELS[MIDI_OUT], kind=MIDI_OUT)
        return [hello, carriage, strip, midi]

    async def serve_lines(self, host: str = "127.0.0.1", port: int = 5555, ready=None) -> None:
        """The same device on a serial-style line link (``tcp://``), like the QEMU build.
        It prints a boot line first, as a real ESP32 does."""

        async def session(reader, writer):
            link = LineLink(reader, writer)
            writer.write(b"ets Jun  8 2016 00:22:57 rst:0x1 (POWERON_RESET),boot:0x13\n")
            await self._session(link)

        server = await asyncio.start_server(session, host, port)
        async with server:
            if ready is not None:
                ready(server.sockets[0].getsockname()[1])
            await asyncio.Future()

    async def _session(self, ws: ServerConnection | LineLink) -> None:
        for msg in self.greeting():
            await ws.send(msg.to_json())
        async for text in ws:
            try:
                replies = self.handle(parse_message(text))
            except (ValueError, TypeError) as exc:
                replies = [(0.0, Ack(status=f"error: {exc}"))]
            for delay, reply in replies:
                if delay:
                    asyncio.get_running_loop().call_later(delay, self._send_later, ws, reply)
                else:
                    await ws.send(reply.to_json())

    def _send_later(self, ws: ServerConnection | LineLink, reply: Message) -> None:
        task = asyncio.ensure_future(ws.send(reply.to_json()))
        task.add_done_callback(_log_failure)

    async def serve(self, host: str = "127.0.0.1", port: int = 8765, ready=None) -> None:
        async with serve(self._session, host, port) as server:
            if ready is not None:
                ready(server.sockets[0].getsockname()[1])
            await asyncio.Future()  # run until cancelled


def _log_failure(task: asyncio.Future) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("simulated device could not send: %r", task.exception())
