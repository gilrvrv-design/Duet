"""A simulated rig device on a real WebSocket (spec §9.1 digital twin).

It behaves like the ESP32 will: it answers clock pings with its own clock, acknowledges
every command, queues timed commands and runs them against the physics simulator.
Its clock is offset from the Hub on purpose, so clock sync is really exercised.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from websockets.asyncio.server import ServerConnection, serve

from duet.device.clock import hub_now_us
from duet.profile import RobotProfile, robot_profile
from duet.protocol import Ack, Hello, Message, TimePing, TimePong, parse_message
from duet.sim import SimulatedRig


@dataclass
class SimulatedDevice:
    profile: RobotProfile = field(default_factory=robot_profile)
    clock_offset_us: int = 987_654_321
    drift_ppm: float = 0.0  # a real crystal is off by tens of ppm
    device_id: str = "sim-1"
    rig: SimulatedRig = field(init=False)
    commands: int = 0

    def __post_init__(self) -> None:
        self.rig = SimulatedRig(self.profile)
        self._start = hub_now_us()

    def now_us(self) -> int:
        return round(self.true_device_time(hub_now_us()))

    def true_device_time(self, hub_us: int) -> float:
        """The device clock at a Hub time: what sync tries to learn."""
        return hub_us + self.clock_offset_us + self.drift_ppm * (hub_us - self._start) / 1e6

    def handle(self, msg: Message) -> Message | None:
        if isinstance(msg, TimePing):
            arrived = self.now_us()
            return TimePong(msg.t1, arrived, self.now_us(), seq=msg.seq)
        self.rig.send(msg)
        self.commands += 1
        return Ack(seq=msg.seq)

    async def _session(self, ws: ServerConnection) -> None:
        await ws.send(Hello(device_id=self.device_id, profile=self.profile.id).to_json())
        async for text in ws:
            try:
                reply = self.handle(parse_message(text))
            except (ValueError, TypeError) as exc:
                reply = Ack(status=f"error: {exc}")
            if reply is not None:
                await ws.send(reply.to_json())

    async def serve(self, host: str = "127.0.0.1", port: int = 8765, ready=None) -> None:
        async with serve(self._session, host, port) as server:
            if ready is not None:
                ready(server.sockets[0].getsockname()[1])
            await asyncio.Future()  # run until cancelled
