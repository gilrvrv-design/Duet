"""A simulated rig (spec §9.1 digital twin): runs device messages against the physics.

It does not trust the plan. It enforces the same safety rules as the firmware
(``firmware/lib/duet_core``) and reports the same fault codes, so the contract test can
compare the two on bad command streams as well as good ones. It also knows where the
bottles are, which the firmware does not, so it can tell a strike that misses a bottle.
It runs offline (all messages, then time order), so it does not model the watchdog.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from duet.device.limits import STRIKE_HISTORY, DeviceLimits
from duet.kinematics import move_time_s
from duet.plans import HOME_STEPS
from duet.profile import RobotProfile
from duet.protocol import (
    CARRIAGE_STRIKER,
    CHANNEL_KIND,
    LED_STRIP,
    MIDI_OUT,
    Estop,
    Home,
    LedFrameAt,
    Message,
    MoveAt,
    NoteAt,
    StrikeAt,
    message_time_us,
)


@dataclass(frozen=True)
class Sound:
    t_us: int
    pitch: int


@dataclass(frozen=True)
class LedFrame:
    t_us: int
    first: int
    count: int
    rgb: tuple[int, int, int]


@dataclass(frozen=True)
class SimFault:
    t_us: int
    code: str  # firmware fault codes, plus OFF_BOTTLE (Hub-side only)
    detail: str

    def __str__(self) -> str:
        return f"t={self.t_us}: {self.code}: {self.detail}"


RIG_CHANNELS = {CARRIAGE_STRIKER: 0, LED_STRIP: 1, MIDI_OUT: 2}  # as firmware/boards/*/board.h
RIG_LEDS = 176  # as LED_COUNT in firmware/src/rig.h


@dataclass
class SimulatedRig:
    """The rig: a carriage-striker on channel 0, an LED strip on 1 and MIDI out on 2, like
    the boards in firmware/boards/ (the contract test keeps them the same)."""

    profile: RobotProfile
    limits: DeviceLimits | None = None  # default: what the profile says
    sounds: list[Sound] = field(default_factory=list)
    led_frames: list[LedFrame] = field(default_factory=list)
    notes: list[NoteAt] = field(default_factory=list)  # MIDI out, on and off
    faults: list[SimFault] = field(default_factory=list)
    received: list[Message] = field(default_factory=list)
    position: int = HOME_STEPS
    target: int = HOME_STEPS
    arrives_us: int = 0
    homed: bool = False
    stopped: bool = False
    _strikes: deque = field(default_factory=lambda: deque(maxlen=STRIKE_HISTORY))

    def __post_init__(self) -> None:
        self.limits = self.limits or DeviceLimits.from_profile(self.profile)

    @property
    def fault_codes(self) -> list[str]:
        return [f.code for f in self.faults]

    @property
    def channels(self) -> dict[str, int]:
        return dict(RIG_CHANNELS)

    def send(self, msg: Message) -> None:
        kind = CHANNEL_KIND.get(type(msg))
        if kind is not None and msg.ch != RIG_CHANNELS[kind]:
            # The firmware refuses it ("no such channel"): a Hub bug, so say so loudly.
            raise ValueError(
                f"{msg.type} for channel {msg.ch}; this rig's {kind} is {RIG_CHANNELS[kind]}"
            )
        self.received.append(msg)

    def run(self) -> None:
        """Execute everything received, in time order (the device's command queue)."""
        queue = sorted(self.received, key=lambda m: (message_time_us(m), m.seq))
        self.received = []
        for msg in queue:
            self._execute(msg)

    def _fault(self, t_us: int, code: str, detail: str) -> None:
        self.faults.append(SimFault(t_us, code, detail))

    def _execute(self, msg: Message) -> None:
        if isinstance(msg, Estop):
            self.stopped = True  # latched, like the firmware
            return
        if self.stopped:
            return
        if isinstance(msg, Home):
            self.position = HOME_STEPS
            self.arrives_us = 0
            self.homed = True
        elif isinstance(msg, MoveAt):
            self._move(msg)
        elif isinstance(msg, StrikeAt):
            self._strike(msg)
        elif isinstance(msg, LedFrameAt):
            self.led_frames.append(LedFrame(msg.t_us, msg.first, msg.count, msg.rgb))
        elif isinstance(msg, NoteAt):  # no carriage, no homing needed
            self.notes.append(msg)

    def _move(self, msg: MoveAt) -> None:
        if not self.homed:
            return self._fault(msg.t_us, "NOT_HOMED", "move before homing")
        if not 0 <= msg.target_steps <= self.limits.travel_steps:
            return self._fault(msg.t_us, "SOFT_LIMIT", "target outside travel")
        if msg.t_us < self.arrives_us:
            self._fault(msg.t_us, "MOVE_OVERLAP", "move started before the last one ended")
        travel = move_time_s(self.position, msg.target_steps, self.profile.kinematics)
        self.position = msg.target_steps
        self.arrives_us = msg.t_us + round(travel * 1_000_000)

    def _strike(self, msg: StrikeAt) -> None:
        if not self.homed:
            return self._fault(msg.t_us, "NOT_HOMED", "strike before homing")
        if msg.t_us < self.arrives_us:
            return self._fault(msg.t_us, "NOT_ARRIVED", "strike before the carriage arrived")
        pulse = min(msg.pulse_us, self.limits.max_pulse_us)
        if pulse <= 0:
            return None
        if not self._duty_allows(msg.t_us, pulse):
            return self._fault(msg.t_us, "DUTY_CYCLE", "solenoid duty limit reached")
        bottle = next((b for b in self.profile.notes if b.steps == self.position), None)
        if bottle is None:
            return self._fault(msg.t_us, "OFF_BOTTLE", "strike away from any bottle")
        latency = round(self.profile.striker.latency_ms * 1000)
        self.sounds.append(Sound(msg.t_us + latency, bottle.midi))
        return None

    def _duty_allows(self, t_us: int, pulse_us: int) -> bool:
        """Same rule as Executor::duty_allows: on-time within the window, and refuse
        once the strike history is full of strikes still inside the window."""
        window = self.limits.duty_window_us
        if len(self._strikes) == STRIKE_HISTORY and t_us - self._strikes[0][0] < window:
            return False
        on = pulse_us + sum(p for t, p in self._strikes if t_us - t < window)
        if on > self.limits.duty_limit * window:
            return False
        self._strikes.append((t_us, pulse_us))
        return True
