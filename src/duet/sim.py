"""A simulated rig (spec §9.1 digital twin): runs device messages against the physics.

It does not trust the plan. It tracks where the carriage really is and reports a
fault if a strike happens before the carriage arrives or away from a bottle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duet.kinematics import move_time_s
from duet.plans import HOME_STEPS
from duet.profile import RobotProfile
from duet.protocol import Estop, Home, LedFrameAt, Message, MoveAt, StrikeAt, message_time_us


@dataclass(frozen=True)
class Sound:
    t_us: int
    pitch: int
    pulse_us: int


@dataclass(frozen=True)
class LedFrame:
    t_us: int
    first: int
    count: int
    rgb: tuple[int, int, int]


@dataclass
class SimulatedRig:
    profile: RobotProfile
    sounds: list[Sound] = field(default_factory=list)
    led_frames: list[LedFrame] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    received: list[Message] = field(default_factory=list)
    position: int = HOME_STEPS
    arrives_us: int = 0
    stopped: bool = False

    def send(self, msg: Message) -> None:
        self.received.append(msg)

    def run(self) -> None:
        """Execute everything received, in time order (the device's command queue)."""
        queue = sorted(self.received, key=lambda m: (message_time_us(m), m.seq))
        self.received = []
        for msg in queue:
            self._execute(msg)

    def _execute(self, msg: Message) -> None:
        if isinstance(msg, Estop):
            self.stopped = True
            return
        if self.stopped:
            return
        if isinstance(msg, Home):
            self.position, self.arrives_us = HOME_STEPS, 0
        elif isinstance(msg, MoveAt):
            if msg.t_us < self.arrives_us:
                self.faults.append(f"t={msg.t_us}: move starts before the last move ended")
            travel = move_time_s(self.position, msg.target_steps, self.profile.kinematics)
            self.position = msg.target_steps
            self.arrives_us = msg.t_us + round(travel * 1_000_000)
        elif isinstance(msg, StrikeAt):
            bottle = next((b for b in self.profile.notes if b.steps == self.position), None)
            if msg.t_us < self.arrives_us:
                self.faults.append(f"t={msg.t_us}: strike before the carriage arrived")
            elif bottle is None:
                self.faults.append(f"t={msg.t_us}: strike away from any bottle")
            else:
                latency = round(self.profile.striker.latency_ms * 1000)
                self.sounds.append(Sound(msg.t_us + latency, bottle.midi, msg.pulse_us))
        elif isinstance(msg, LedFrameAt):
            self.led_frames.append(LedFrame(msg.t_us, msg.first, msg.count, msg.rgb))
