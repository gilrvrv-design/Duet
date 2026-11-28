"""Fixed-tempo performance (spec §5.5, Phase 0).

The conductor turns a checked score into timed device messages and sends them ahead
of time, so jitter on the link does not reach the music.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from duet.device.clock import hub_now_us
from duet.listening import KeyInput
from duet.plans import HOME_STEPS, LedCue, RobotPlan, led_plan, robot_plan
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import Home, LedFrameAt, Message, MoveAt, StrikeAt, message_time_us
from duet.score import DuetScore, Performer
from duet.timing import seconds_per_beat, timed_events

OFF = (0, 0, 0)


class State(StrEnum):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    COUNT_IN = "COUNT_IN"
    PLAYING = "PLAYING"
    WAITING = "WAITING"
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
    performer: Performer
    t_us: int
    pitch: int
    bar: int = 0


@dataclass
class Performance:
    start_us: int = 0  # clock time of bar 1 beat 1
    planned: list[PlannedNote] = field(default_factory=list)
    states: list[State] = field(default_factory=lambda: [State.IDLE])
    messages_sent: int = 0
    waited_us: int = 0  # total time spent waiting for the pianist (wait mode)
    played: list = field(default_factory=list)  # what the pianist played, if heard
    follow_matches: list = field(default_factory=list)  # follow mode: (score us, clock us)
    final_rate: float = 1.0  # follow mode: clock time per score time at the end
    end_steps: int = 0  # where the carriage is when the piece ends

    def expected_pianist(self):
        from duet.listening import Expected

        return [Expected(p.t_us, p.pitch, p.bar) for p in self.planned if p.performer == "human"]


def home_all(devices: list[Device], timeout_s: float = 30.0) -> None:
    """Home every device and wait until each reports it is homed (FR-R5)."""
    for device in devices:
        device.send(Home())
    for device in devices:  # a real carriage takes time to find home
        wait_ready = getattr(device, "wait_ready", None)
        if wait_ready is not None:
            wait_ready(timeout_s)


def build_messages(
    score: DuetScore,
    robot: RobotProfile,
    keyboard: KeyboardProfile,
    start_us: int,
    start_steps: int = HOME_STEPS,
    count_in: bool = True,
    plan: RobotPlan | None = None,
) -> tuple[list[Message], list[PlannedNote]]:
    """All device messages for one performance of a duet (one bot part, one human part),
    sorted by time. Pass ``plan`` when it was already made from the same score, robot
    and start position."""
    bot, human = score.part_played_by("bot"), score.part_played_by("human")

    def us(seconds: float) -> int:
        return start_us + round(seconds * 1_000_000)

    plan = plan or robot_plan(score, robot, start_steps, part=bot)
    kin = robot.kinematics
    spb = seconds_per_beat(score.meta.tempo_bpm)
    messages: list[Message] = []
    planned = []
    for cmd in plan.commands:
        if cmd.move_s > 0:
            messages.append(
                MoveAt(us(cmd.move_start_s), cmd.target_steps, kin.v_max_mm_s, kin.a_max_mm_s2)
            )
        messages.append(StrikeAt(us(cmd.fire_s), cmd.pulse_us))
        bar = 1 + int(cmd.sound_s / spb // score.meta.beats_per_bar)
        planned.append(PlannedNote(bot, "bot", us(cmd.sound_s), robot.pitches[cmd.bottle], bar))
    for cue in led_plan(score, keyboard, count_in_bars=1 if count_in else 0, part=human):
        messages.extend(_led_messages(cue, us))
    planned += [
        PlannedNote(human, "human", us(t.start_s), t.event.pitch, t.event.bar)
        for t in timed_events(score, human)
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
    keys: KeyInput | None = None,
    mode: str = "wait",
    home: bool = True,
    count_in: bool = True,
    start_steps: int = HOME_STEPS,
    start_at_us: int | None = None,
) -> Performance:
    """Play a score: home, count in, then stream messages ``lookahead_s`` ahead of time.

    With ``keys``: in "wait" mode the performance pauses at every pianist note until the
    pianist plays it, and everything after shifts by the wait; in "follow" mode the robot
    follows the pianist's tempo.

    For back-to-back pieces (call and response), pass ``home=False``, ``count_in=False``,
    the carriage position the last piece ended at, and when to start.
    """
    perf = Performance()
    perf.states.append(State.PREPARING)
    if home:
        home_all(devices, homing_timeout_s)
        start_steps = HOME_STEPS
    plan = robot_plan(score, robot, start_steps, part=score.part_played_by("bot"))
    count_in_s = (
        score.meta.beats_per_bar * seconds_per_beat(score.meta.tempo_bpm) if count_in else 0
    )
    earliest = clock.now_us() + round((buffer_s + max(count_in_s, plan.preroll_s)) * 1_000_000)
    perf.start_us = earliest if start_at_us is None else max(start_at_us, earliest)
    perf.end_steps = plan.commands[-1].target_steps if plan.commands else start_steps
    messages, perf.planned = build_messages(
        score, robot, keyboard, perf.start_us, start_steps, count_in, plan
    )

    perf.states.append(State.COUNT_IN)
    sender = _Sender(devices, keys, perf, robot, start_steps)
    if keys is not None and mode == "follow":
        return _follow(perf, messages, score, robot, sender, clock, keys)
    gates = _gates(perf.planned) if keys is not None else []
    shifts: list[tuple[int, int]] = []  # (original gate time, total delay from then on)
    delay = 0
    lookahead_us = round(lookahead_s * 1_000_000)

    def wait_for_pianist(msg: Message) -> None:
        nonlocal delay
        while gates and message_time_us(msg) >= gates[0][0]:
            # Nothing at or after the next pianist note is sent until it is played,
            # because its time is not known yet (wait mode, FR-P2).
            gate_t, pitches = gates.pop(0)
            cue = gate_t + delay
            clock.sleep_until(cue)
            perf.states.append(State.WAITING)
            pressed = keys.wait_for(pitches, cue - EARLY_PRESS_US, clock)
            delay += max(0, pressed - cue)
            shifts.append((gate_t, delay))
            perf.states.append(State.PLAYING)

    def send(msg: Message) -> None:
        if State.PLAYING not in perf.states and clock.now_us() >= perf.start_us - lookahead_us:
            perf.states.append(State.PLAYING)
        sender.send(msg)

    stream(
        messages,
        clock,
        lookahead_us,
        send,
        before=wait_for_pianist,
        time_of=lambda m: message_time_us(m) + delay,
    )
    if State.PLAYING not in perf.states:
        perf.states.append(State.PLAYING)
    perf.waited_us = delay
    if keys is not None:
        perf.played = list(keys.played)
        perf.planned = [_shifted(p, shifts) for p in perf.planned]
    perf.states += [State.ENDING, State.REVIEW]
    return perf


def stream(
    messages: list[Message],
    clock: Clock,
    lookahead_us: int,
    send: Callable[[Message], None],
    before: Callable[[Message], None] | None = None,
    time_of: Callable[[Message], int] = message_time_us,
) -> None:
    """Send each message ``lookahead_us`` before its time. ``before`` runs first for each
    message (wait mode blocks there for the pianist); ``time_of`` gives its final time."""
    for msg in messages:
        if before is not None:
            before(msg)
        t = time_of(msg)
        clock.sleep_until(t - lookahead_us)
        send(msg if t == message_time_us(msg) else replace(msg, t_us=t))


class _Sender:
    """Sends to every device, and tells a listening key input when the robot will sound,
    so a microphone can tell the bottles from the piano (FR-H2).

    A strike's pitch is the bottle the carriage was last sent to: what will really
    sound, whatever order or timing the messages are sent in."""

    def __init__(
        self, devices, keys, perf: Performance, robot: RobotProfile, start_steps: int
    ) -> None:
        self.devices = devices
        self.perf = perf
        self.hook = getattr(keys, "robot_strike", None)
        self.pitch_at = {
            note.steps: pitch for pitch, note in zip(robot.pitches, robot.notes, strict=True)
        }
        self.position = start_steps
        self.latency_us = round(robot.striker.latency_ms * 1000)

    def send(self, msg: Message) -> None:
        for device in self.devices:
            device.send(msg)
        self.perf.messages_sent += 1
        if isinstance(msg, MoveAt):
            self.position = msg.target_steps
        elif isinstance(msg, StrikeAt) and self.hook is not None:
            pitch = self.pitch_at.get(self.position)
            if pitch is not None:
                self.hook(msg.t_us + self.latency_us, pitch)


EARLY_PRESS_US = 300_000  # a key pressed this soon before its cue still counts
FOLLOW_LOOKAHEAD_US = 150_000  # short, so tempo changes reach the robot quickly


def _follow(perf, messages, score, robot, sender, clock, keys) -> Performance:
    """Follow mode: every command is timed through the follower's current tempo map."""
    from duet.feasibility import max_speed_up
    from duet.follow import Follower

    follower = Follower(
        perf.expected_pianist(),
        min_rate=1 / max_speed_up(score, robot, part=score.part_played_by("bot")),
    )
    begin = getattr(keys, "begin", None)
    if begin is not None:  # a simulated pianist needs to know when to play
        begin(perf.expected_pianist())
    follower.anchor_score_us = follower.anchor_clock_us = perf.start_us
    perf.states.append(State.PLAYING)

    def listen():
        for note in keys.poll(clock):
            follower.hear(note)

    # A move's travel time is physical: time it back from its own strike, never scale it.
    lead_of = _move_leads(messages)
    arrival = 0  # clock time the carriage reaches the target of the last move sent

    def when(msg) -> int:
        if isinstance(msg, MoveAt):
            strike_t, lead = lead_of[msg.seq]
            return follower.to_clock(strike_t) - lead
        t = follower.to_clock(message_time_us(msg))
        return max(t, arrival) if isinstance(msg, StrikeAt) else t

    for msg in messages:
        while True:
            target = when(msg) - FOLLOW_LOOKAHEAD_US
            upcoming = keys.next_event_us(clock)
            if upcoming is not None and upcoming < target:
                clock.sleep_until(upcoming)
                listen()
                continue
            clock.sleep_until(target)
            listen()
            if when(msg) - FOLLOW_LOOKAHEAD_US <= clock.now_us():
                break
        t = max(clock.now_us(), when(msg))
        if isinstance(msg, MoveAt):
            arrival = t + lead_of[msg.seq][1]
        sender.send(replace(msg, t_us=t))
    perf.played = list(keys.played)
    perf.follow_matches = list(follower.matches)
    perf.final_rate = follower.rate
    perf.states += [State.ENDING, State.REVIEW]
    return perf


def _move_leads(messages) -> dict[int, tuple[int, int]]:
    """For each move: (time of the strike it serves, how long before it the move starts)."""
    leads, pending = {}, None
    for msg in messages:
        if isinstance(msg, MoveAt):
            pending = msg
        elif isinstance(msg, StrikeAt) and pending is not None:
            leads[pending.seq] = (msg.t_us, msg.t_us - pending.t_us)
            pending = None
    return leads


def _gates(planned: list[PlannedNote]) -> list[tuple[int, frozenset[int]]]:
    """The human's onsets (and the keys at each) in time order."""
    by_time: dict[int, set[int]] = {}
    for p in planned:
        if p.performer == "human":
            by_time.setdefault(p.t_us, set()).add(p.pitch)
    return [(t, frozenset(keys)) for t, keys in sorted(by_time.items())]


def _shifted(p: PlannedNote, shifts: list[tuple[int, int]]) -> PlannedNote:
    applied = 0
    for gate_t, total in shifts:
        if p.t_us >= gate_t:
            applied = total
    return replace(p, t_us=p.t_us + applied) if applied else p
