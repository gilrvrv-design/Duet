"""Fixed-tempo performance (spec §5.5, Phase 0).

The conductor turns a checked score into timed device messages and sends them ahead
of time, so jitter on the link does not reach the music.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from duet.device.clock import hub_now_us
from duet.plans import LedCue, led_plan, robot_plan
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import Home, LedFrameAt, Message, MoveAt, StrikeAt, message_time_us
from duet.score import DuetScore
from duet.timing import seconds_per_beat, timed_events

OFF = (0, 0, 0)


class State(StrEnum):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    COUNT_IN = "COUNT_IN"
    PLAYING = "PLAYING"
    ENDING = "ENDING"
    REVIEW = "REVIEW"
    FAULT = "FAULT"


class Device(Protocol):
    def send(self, msg: Message) -> None: ...


class Clock(Protocol):
    def now_us(self) -> int: ...
    def sleep_until(self, t_us: int) -> None: ...


class RealClock:
    def now_us(self) -> int:
        return hub_now_us()

    def sleep_until(self, t_us: int) -> None:
        delay = (t_us - self.now_us()) / 1_000_000
        if delay > 0:
            time.sleep(delay)


@dataclass
class VirtualClock:
    t_us: int = 0

    def now_us(self) -> int:
        return self.t_us

    def sleep_until(self, t_us: int) -> None:
        self.t_us = max(self.t_us, t_us)


@dataclass(frozen=True)
class PlannedNote:
    part: str
    t_us: int
    pitch: int


@dataclass
class Performance:
    start_us: int = 0  # clock time of bar 1 beat 1
    planned: list[PlannedNote] = field(default_factory=list)
    states: list[State] = field(default_factory=lambda: [State.IDLE])
    messages_sent: int = 0


def build_messages(
    score: DuetScore,
    robot: RobotProfile,
    keyboard: KeyboardProfile,
    start_us: int,
) -> tuple[list[Message], list[PlannedNote]]:
    """All device messages for one performance, sorted by time."""

    def us(seconds: float) -> int:
        return start_us + round(seconds * 1_000_000)

    plan = robot_plan(score, robot)
    kin = robot.kinematics
    messages: list[Message] = []
    planned = []
    for cmd in plan.commands:
        if cmd.move_s > 0:
            messages.append(
                MoveAt(us(cmd.move_start_s), cmd.target_steps, kin.v_max_mm_s, kin.a_max_mm_s2)
            )
        messages.append(StrikeAt(us(cmd.fire_s), cmd.pulse_us))
        planned.append(PlannedNote("robot", us(cmd.sound_s), robot.pitches[cmd.bottle]))
    for cue in led_plan(score, keyboard):
        messages.extend(_led_messages(cue, us))
    planned += [
        PlannedNote("pianist", us(t.start_s), t.event.pitch) for t in timed_events(score, "pianist")
    ]
    messages.sort(key=message_time_us)
    numbered = [replace(m, seq=i) for i, m in enumerate(messages)]
    return numbered, sorted(planned, key=lambda p: (p.t_us, p.part))


def _led_messages(cue: LedCue, us) -> list[Message]:
    return [
        LedFrameAt(us(cue.on_s), cue.first_led, cue.count, cue.color),
        LedFrameAt(us(cue.off_s), cue.first_led, cue.count, OFF),
    ]


def perform(
    score: DuetScore,
    robot: RobotProfile,
    keyboard: KeyboardProfile,
    devices: list[Device],
    clock: Clock,
    lookahead_s: float = 0.5,
    buffer_s: float = 0.3,
    homing_timeout_s: float = 30.0,
) -> Performance:
    """Play a score: home, count in, then stream messages ``lookahead_s`` ahead of time."""
    perf = Performance()
    perf.states.append(State.PREPARING)
    for device in devices:
        device.send(Home())
    for device in devices:  # a real carriage takes time to find home (FR-R5)
        wait_ready = getattr(device, "wait_ready", None)
        if wait_ready is not None:
            wait_ready(homing_timeout_s)
    count_in_s = score.meta.beats_per_bar * seconds_per_beat(score.meta.tempo_bpm)
    preroll = robot_plan(score, robot).preroll_s
    perf.start_us = clock.now_us() + round((buffer_s + max(count_in_s, preroll)) * 1_000_000)
    messages, perf.planned = build_messages(score, robot, keyboard, perf.start_us)

    perf.states.append(State.COUNT_IN)
    playing = False
    lookahead_us = round(lookahead_s * 1_000_000)
    for msg in messages:
        t = message_time_us(msg)
        clock.sleep_until(t - lookahead_us)
        if not playing and clock.now_us() >= perf.start_us - lookahead_us:
            perf.states.append(State.PLAYING)
            playing = True
        for device in devices:
            device.send(msg)
        perf.messages_sent += 1
    if not playing:
        perf.states.append(State.PLAYING)
    perf.states += [State.ENDING, State.REVIEW]
    return perf
