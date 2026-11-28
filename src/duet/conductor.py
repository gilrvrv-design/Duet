"""Fixed-tempo performance (spec §5.5, Phase 0).

The conductor turns a checked score into timed device messages and sends them ahead
of time, so jitter on the link does not reach the music.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from duet import midi_bot
from duet.device.clock import hub_now_us
from duet.feasibility import max_speed_up
from duet.follow import Follower
from duet.listening import Expected, KeyInput, listen_until
from duet.performers import NO_OVERRIDES, Bot, Instruments, performers
from duet.plans import HOME_STEPS, LedCue, RobotPlan, led_plan, robot_plan
from duet.protocol import CHANNEL_KIND, Home, LedFrameAt, Message, MoveAt, StrikeAt, message_time_us
from duet.score import DuetScore, PerformerKind
from duet.timing import seconds_per_beat, timed_events

OFF = (0, 0, 0)

EARLY_PRESS_US = 300_000  # a key pressed this soon before its cue still counts
FOLLOW_LOOKAHEAD_US = 150_000  # short, so tempo changes reach the robot quickly


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
    """Anything that plays messages: a rig over the gateway, a simulator, a recorder.
    ``channels`` is what it drives, by kind (its greeting): the conductor sends each
    timed message to the device's channel of that message's kind."""

    channels: Mapping[str, int]

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
    performer: PerformerKind
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
    final_rate: float = 1.0  # follow mode: clock time per score time at the end
    end_steps: dict[str, int] = field(default_factory=dict)  # bot part -> carriage at the end

    def expected_pianist(self):
        return [Expected(p.t_us, p.pitch, p.bar) for p in self.planned if p.performer == "human"]


def send_to(device: Device, msg: Message) -> None:
    """Send a timed message on the device's channel of its kind (the one place a
    message's ``ch`` is filled in)."""
    device.send(replace(msg, ch=device.channels[CHANNEL_KIND[type(msg)]]))


def home_all(devices: list[Device], timeout_s: float = 30.0) -> None:
    """Home every device and wait until each reports it is homed (FR-R5)."""
    for device in devices:
        device.send(Home())
    for device in devices:  # a real carriage takes time to find home
        wait_ready = getattr(device, "wait_ready", None)
        if wait_ready is not None:
            wait_ready(timeout_s)


Routes = Mapping[str, Sequence[Device]]  # part -> the devices that play it


def one_rig(score: DuetScore, devices: Sequence[Device]) -> dict[str, list[Device]]:
    """Every part on the same devices: the usual rig, where one board drives the bot and
    lights the keys for the person."""
    return {part: list(devices) for part in score.parts}


@dataclass(frozen=True)
class Program:
    """Everything a performance sends, in time order, and which part each message is for."""

    messages: list[Message]
    part_of: dict[int, str]  # message seq -> part
    planned: list[PlannedNote]
    plans: dict[str, RobotPlan]  # bot part -> its carriage plan

    def at(self, start_us: int) -> Program:
        """The same program with bar 1 beat 1 at ``start_us`` (it was built for 0)."""
        return Program(
            [replace(m, t_us=message_time_us(m) + start_us) for m in self.messages],
            self.part_of,
            [replace(n, t_us=n.t_us + start_us) for n in self.planned],
            self.plans,
        )


def build_messages(
    score: DuetScore,
    start_us: int,
    *,
    instruments: Instruments = NO_OVERRIDES,
    start_steps: Mapping[str, int] | None = None,
    count_in: bool = True,
) -> Program:
    """Every part's messages: each bot part's moves and strikes, each human part's light
    cues (the first human part's lights also count everyone in). ``start_steps``: where
    each bot's carriage is now (default: home)."""
    start_steps = start_steps or {}

    def us(seconds: float) -> int:
        return start_us + round(seconds * 1_000_000)

    tagged: list[tuple[str, Message]] = []
    planned: list[PlannedNote] = []
    plans: dict[str, RobotPlan] = {}
    counted_in = not count_in
    for p in performers(score, instruments):
        if isinstance(p, Bot) and not p.moves:  # MIDI out: a note on and a note off each
            tagged += [(p.part, m) for m in midi_bot.messages(score, p.part, p.instrument, us)]
            planned += [
                PlannedNote(p.part, "bot", us(t.start_s), t.event.pitch, t.event.bar)
                for t in timed_events(score, p.part)
            ]
        elif isinstance(p, Bot):
            robot = p.profile
            plan = robot_plan(score, robot, start_steps.get(p.part, HOME_STEPS), part=p.part)
            plans[p.part] = plan
            kin = robot.kinematics
            for cmd in plan.commands:
                if cmd.move_s > 0:
                    move = MoveAt(
                        us(cmd.move_start_s), cmd.target_steps, kin.v_max_mm_s, kin.a_max_mm_s2
                    )
                    tagged.append((p.part, move))
                tagged.append((p.part, StrikeAt(us(cmd.fire_s), cmd.pulse_us)))
                pitch = robot.pitches[cmd.bottle]
                planned.append(PlannedNote(p.part, "bot", us(cmd.sound_s), pitch, cmd.bar))
        else:
            cues = led_plan(score, p.profile, count_in_bars=0 if counted_in else 1, part=p.part)
            counted_in = True
            tagged += [(p.part, m) for cue in cues for m in _led_messages(cue, us)]
            planned += [
                PlannedNote(p.part, "human", us(t.start_s), t.event.pitch, t.event.bar)
                for t in timed_events(score, p.part)
            ]
    tagged.sort(key=lambda pm: message_time_us(pm[1]))
    messages = [replace(m, seq=i) for i, (_, m) in enumerate(tagged)]
    part_of = {i: part for i, (part, _) in enumerate(tagged)}
    planned.sort(key=lambda n: (n.t_us, n.part))
    return Program(messages, part_of, planned, plans)


def _led_messages(cue: LedCue, us) -> list[Message]:
    return [
        LedFrameAt(us(cue.on_s), cue.first_led, cue.count, cue.color),
        LedFrameAt(us(cue.off_s), cue.first_led, cue.count, OFF),
    ]


def _check_routes(score: DuetScore, routes: Routes, instruments: Instruments) -> None:
    """Every part has its devices, and no device carries two bots that move: one
    carriage cannot be in two places. (MIDI parts can share a device's MIDI out.)"""
    missing = [part for part in score.parts if part not in routes]
    if missing:
        raise ValueError(f"no devices for part(s) {missing}: route every part, even to []")
    owner: dict[int, str] = {}
    for part in _moving_bots(score, instruments):
        for device in routes[part]:
            other = owner.setdefault(id(device), part)
            if other != part:
                raise ValueError(f"parts {other!r} and {part!r} would drive the same device")


def _moving_bots(score: DuetScore, instruments: Instruments) -> list[str]:
    """The parts played by a bot with a carriage."""
    return [p.part for p in performers(score, instruments) if isinstance(p, Bot) and p.moves]


def _check_channels(program: Program, routes: Routes) -> None:
    """Every device a part is routed to drives what that part's messages need: a
    carriage for a bot's strikes, an LED strip for a person's cues."""
    needs: dict[str, set[str]] = {}
    for msg in program.messages:
        needs.setdefault(program.part_of[msg.seq], set()).add(CHANNEL_KIND[type(msg)])
    for part, kinds in needs.items():
        for device in routes[part]:
            missing = kinds - set(device.channels)
            if missing:
                raise ValueError(
                    f"part {part!r}: a device it is routed to has no {sorted(missing)}"
                )


def perform(
    score: DuetScore,
    routes: Routes,
    clock: Clock,
    *,
    instruments: Instruments = NO_OVERRIDES,
    lookahead_s: float = 0.5,
    buffer_s: float = 0.3,
    homing_timeout_s: float = 30.0,
    keys: KeyInput | None = None,
    mode: str = "wait",
    home: bool = True,
    count_in: bool = True,
    start_steps: Mapping[str, int] | None = None,
    start_at_us: int | None = None,
) -> Performance:
    """Play a score: home, count in, then stream every part's messages to its devices
    (``routes``) ``lookahead_s`` ahead of time. ``instruments``: the ones in use, before
    the built-in ones (say, a calibrated rig).

    With ``keys``: in "wait" mode the performance pauses at every note of the human
    parts until it is played, and everything after shifts by the wait; in "follow" mode
    the bots follow the humans' tempo.

    For back-to-back pieces (call and response), pass ``home=False``, ``count_in=False``,
    where each bot's carriage is (``start_steps``), and when to start.
    """
    if mode not in ("wait", "follow"):
        raise ValueError(f"mode {mode!r}: wait or follow")
    _check_routes(score, routes, instruments)
    perf = Performance()
    _enter(perf, State.PREPARING)
    if home:
        _home_carriages(score, routes, instruments, homing_timeout_s)
        start_steps = None
    program = _schedule(
        score, perf, clock, instruments, start_steps, count_in, buffer_s, start_at_us
    )
    _check_channels(program, routes)
    _enter(perf, State.COUNT_IN)
    sender = _Sender(routes, program, keys, perf, score, instruments, start_steps or {})
    if keys is not None and mode == "follow":
        return _follow(perf, program, score, instruments, sender, clock, keys)
    lookahead_us = round(lookahead_s * 1_000_000)
    gates = _WaitGates(perf, clock, keys) if keys is not None else None

    def send(msg: Message) -> None:
        if clock.now_us() >= perf.start_us - lookahead_us:
            _enter(perf, State.PLAYING)
        sender.send(msg)

    stream(
        program.messages,
        clock,
        lookahead_us,
        send,
        before=gates.wait_before if gates else None,
        time_of=gates.time_of if gates else message_time_us,
    )
    _enter(perf, State.PLAYING)
    if gates is not None:
        perf.waited_us = gates.delay
        perf.played = list(keys.played)
        perf.planned = [_shifted(p, gates.shifts) for p in perf.planned]
    perf.states += [State.ENDING, State.REVIEW]
    return perf


def _enter(perf: Performance, state: State) -> None:
    """Record reaching ``state``: once, except WAITING and PLAYING, which alternate in
    wait mode and are recorded at each change."""
    repeats = state in (State.WAITING, State.PLAYING)
    if (perf.states[-1] != state) if repeats else (state not in perf.states):
        perf.states.append(state)


def _home_carriages(score, routes: Routes, instruments: Instruments, timeout_s: float) -> None:
    """Home the devices of every bot that moves (each device once)."""
    devices = {id(d): d for part in _moving_bots(score, instruments) for d in routes[part]}
    home_all(list(devices.values()), timeout_s)


def _schedule(
    score, perf: Performance, clock: Clock, instruments, start_steps, count_in, buffer_s,
    start_at_us,
) -> Program:  # fmt: skip
    """When the performance starts (after the count-in, and the carriages' way to their
    first notes), its messages at that time, and where each carriage ends up."""
    program = build_messages(
        score, 0, instruments=instruments, start_steps=start_steps, count_in=count_in
    )
    count_in_s = (
        score.meta.beats_per_bar * seconds_per_beat(score.meta.tempo_bpm) if count_in else 0
    )
    preroll_s = max((plan.preroll_s for plan in program.plans.values()), default=0.0)
    earliest = clock.now_us() + round((buffer_s + max(count_in_s, preroll_s)) * 1_000_000)
    perf.start_us = earliest if start_at_us is None else max(start_at_us, earliest)
    program = program.at(perf.start_us)
    perf.planned = program.planned
    perf.end_steps = {
        part: plan.commands[-1].target_steps
        if plan.commands
        else (start_steps or {}).get(part, HOME_STEPS)
        for part, plan in program.plans.items()
    }
    return program


class _WaitGates:
    """Wait mode (FR-P2): nothing at or after the next human note is sent until that
    note is played, because its time is not known until then; everything after shifts
    by how long the pianist took."""

    def __init__(self, perf: Performance, clock: Clock, keys: KeyInput) -> None:
        self.perf, self.clock, self.keys = perf, clock, keys
        self.pending = _gates(perf.planned)  # (time, pitches) of each human onset
        self.delay = 0  # how long the pianist has been waited for so far
        self.shifts: list[tuple[int, int]] = []  # (original gate time, delay from then on)

    def wait_before(self, msg: Message) -> None:
        while self.pending and message_time_us(msg) >= self.pending[0][0]:
            gate_t, pitches = self.pending.pop(0)
            cue = gate_t + self.delay
            self.clock.sleep_until(cue)
            _enter(self.perf, State.WAITING)
            pressed = self.keys.wait_for(pitches, cue - EARLY_PRESS_US, self.clock)
            self.delay += max(0, pressed - cue)
            self.shifts.append((gate_t, self.delay))
            _enter(self.perf, State.PLAYING)

    def time_of(self, msg: Message) -> int:
        return message_time_us(msg) + self.delay


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
    """Sends each message to its part's devices, and tells a listening key input when
    each bot will sound, so a microphone can tell the instruments from the piano (FR-H2).

    A strike's pitch is the note the bot's carriage was last sent to: what will really
    sound, whatever order or timing the messages are sent in."""

    def __init__(self, routes, program, keys, perf, score, instruments, start_steps) -> None:
        self.routes = routes
        self.part_of = program.part_of
        self.perf = perf
        self.hook = getattr(keys, "robot_strike", None)
        self.carriages: dict[str, _Carriage] = {}
        for p in performers(score, instruments):
            if isinstance(p, Bot) and p.moves:
                robot = p.profile
                self.carriages[p.part] = _Carriage(
                    pitch_at={
                        n.steps: pitch for pitch, n in zip(robot.pitches, robot.notes, strict=True)
                    },
                    position=start_steps.get(p.part, HOME_STEPS),
                    latency_us=round(robot.striker.latency_ms * 1000),
                )

    def send(self, msg: Message) -> None:
        part = self.part_of[msg.seq]
        for device in self.routes[part]:
            send_to(device, msg)
        self.perf.messages_sent += 1
        carriage = self.carriages.get(part)
        if carriage is None:
            return
        if isinstance(msg, MoveAt):
            carriage.position = msg.target_steps
        elif isinstance(msg, StrikeAt) and self.hook is not None:
            pitch = carriage.pitch_at.get(carriage.position)
            if pitch is not None:
                self.hook(msg.t_us + carriage.latency_us, pitch)


@dataclass
class _Carriage:
    pitch_at: dict[int, int]  # steps -> the note there
    position: int
    latency_us: int


def _follow(perf, program, score, instruments, sender, clock, keys) -> Performance:
    """Follow mode: every command is timed through the follower's current tempo map."""
    follower = _follower(perf, score, instruments, keys)
    timing = _FollowTiming(program, follower)
    _enter(perf, State.PLAYING)
    for msg in program.messages:
        # Listen until it is time to send: the tempo, and so the time, may change meanwhile.
        while (target := timing.when(msg) - FOLLOW_LOOKAHEAD_US) > clock.now_us():
            for note in listen_until(keys, clock, target):
                follower.hear(note)
        sender.send(timing.sent(msg, max(clock.now_us(), timing.when(msg))))
    perf.played = list(keys.played)
    perf.final_rate = follower.rate
    perf.states += [State.ENDING, State.REVIEW]
    return perf


def _follower(perf: Performance, score, instruments, keys) -> Follower:
    """A follower of the human parts, never faster than the slowest bot can go."""
    bots = [p for p in performers(score, instruments) if isinstance(p, Bot) and p.moves]
    fastest = min((max_speed_up(score, b.profile, part=b.part) for b in bots), default=1.0)
    follower = Follower(perf.expected_pianist(), min_rate=1 / fastest)
    begin = getattr(keys, "begin", None)
    if begin is not None:  # a simulated pianist needs to know when to play
        begin(perf.expected_pianist())
    follower.anchor_score_us = follower.anchor_clock_us = perf.start_us
    return follower


class _FollowTiming:
    """When each command goes, through the follower's tempo. A move's travel time is
    physical: it is timed back from its own strike, never scaled; a strike waits for
    its carriage to arrive."""

    def __init__(self, program: Program, follower: Follower) -> None:
        self.program, self.follower = program, follower
        self.lead_of = _move_leads(program)
        self.arrival: dict[str, int] = {}  # part -> when its carriage reaches its target

    def when(self, msg: Message) -> int:
        if isinstance(msg, MoveAt):
            strike_t, lead = self.lead_of[msg.seq]
            return self.follower.to_clock(strike_t) - lead
        t = self.follower.to_clock(message_time_us(msg))
        if isinstance(msg, StrikeAt):
            return max(t, self.arrival.get(self.program.part_of[msg.seq], 0))
        return t

    def sent(self, msg: Message, t: int) -> Message:
        if isinstance(msg, MoveAt):
            self.arrival[self.program.part_of[msg.seq]] = t + self.lead_of[msg.seq][1]
        return replace(msg, t_us=t)


def _move_leads(program: Program) -> dict[int, tuple[int, int]]:
    """For each move: (time of the strike it serves, how long before it the move
    starts). A move serves the next strike of the same bot."""
    leads, pending = {}, {}
    for msg in program.messages:
        part = program.part_of[msg.seq]
        if isinstance(msg, MoveAt):
            pending[part] = msg
        elif isinstance(msg, StrikeAt) and part in pending:
            move = pending.pop(part)
            leads[move.seq] = (msg.t_us, msg.t_us - move.t_us)
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
