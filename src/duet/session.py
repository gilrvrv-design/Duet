"""A call-and-response session (spec §5.5 FR-P2 "call & response", §5.7).

Turns alternate: the pianist plays a phrase while the light strip glows "your turn";
the robot answers right after with a variation of it. Repeat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duet.conductor import Clock, Device, home_all, perform
from duet.kinematics import move_time_s
from duet.listening import KeyInput, PlayedNote
from duet.plans import HOME_STEPS, led_count
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import LedFrameAt, MoveAt
from duet.respond import PhraseNote, Responder, capture, reply_score

YOUR_TURN = (0, 40, 90)  # a soft blue over the whole strip
OFF = (0, 0, 0)


@dataclass
class Turn:
    phrase: list[PhraseNote]
    kind: str
    reply: list[PhraseNote]
    pianist_start_us: int
    pianist_end_us: int
    reply_start_us: int


@dataclass
class Session:
    turns: list[Turn] = field(default_factory=list)
    played: list[PlayedNote] = field(default_factory=list)


def call_and_response(
    robot: RobotProfile,
    keyboard: KeyboardProfile,
    devices: list[Device],
    clock: Clock,
    keys: KeyInput,
    tempo_bpm: float = 90,
    bars_per_turn: int = 2,
    turns: int = 4,
    beats_per_bar: int = 4,
) -> Session:
    home_all(devices)
    spb_us = round(60 / tempo_bpm * 1_000_000)
    turn_beats = bars_per_turn * beats_per_bar
    responder = Responder(robot)
    session = Session()
    position = HOME_STEPS
    start = clock.now_us() + beats_per_bar * spb_us  # one bar to get ready
    strip = led_count(keyboard)
    for number in range(turns):
        end = start + turn_beats * spb_us
        for device in devices:
            device.send(LedFrameAt(start, 0, strip, YOUR_TURN))
            device.send(LedFrameAt(end, 0, strip, OFF))
        begin = getattr(keys, "start_turn", None)
        if begin is not None:
            begin(number, start)
        position = _listen_and_preposition(
            keys, clock, start, end, responder, robot, devices, position
        )
        phrase = capture(keys.played, start, tempo_bpm, turn_beats)
        kind, notes = responder.respond(phrase)
        reply_at = end
        if notes:
            perf = perform(
                reply_score(notes, tempo_bpm, robot, beats_per_bar),
                robot,
                keyboard,
                devices,
                clock,
                home=False,
                count_in=False,
                start_steps=position,
                start_at_us=end,
                buffer_s=0.05,
            )
            position, reply_at = perf.end_steps, perf.start_us
        session.turns.append(Turn(phrase, kind, notes, start, end, reply_at))
        start = reply_at + turn_beats * spb_us  # the pianist's next turn follows the answer
    session.played = list(keys.played)
    return session


def _listen_and_preposition(keys, clock, start, end, responder, robot, devices, position) -> int:
    """Listen until the turn ends. Meanwhile move the carriage to where the answer will
    probably start, so the robot can answer within a beat (FR-G1). Returns its position."""
    kin = robot.kinematics
    busy_until = 0

    def reposition() -> None:
        nonlocal position, busy_until
        heard = [p.pitch for p in keys.played if p.t_us >= start]
        guess = responder.predict_first(heard)
        now = clock.now_us()
        if guess is None or now < busy_until:
            return
        target = robot.notes[guess].steps
        if target == position:
            return
        t = now + 20_000
        for device in devices:
            device.send(MoveAt(t, target, kin.v_max_mm_s, kin.a_max_mm_s2))
        busy_until = t + round(move_time_s(position, target, kin) * 1_000_000)
        position = target

    reposition()  # a recall answer is known before the pianist plays anything
    while True:
        upcoming = keys.next_event_us(clock)
        if upcoming is None or upcoming >= end:
            clock.sleep_until(end)
            keys.poll(clock)
            return position
        clock.sleep_until(upcoming)
        if keys.poll(clock):
            reposition()


@dataclass
class PhrasePianist:
    """A simulated pianist who plays a prepared phrase in each turn (beat, pitch)."""

    phrases: list[list[tuple[float, int]]]
    tempo_bpm: float
    played: list[PlayedNote] = field(default_factory=list)
    _schedule: list[PlayedNote] = field(default_factory=list)

    def start_turn(self, number: int, start_us: int) -> None:
        spb = 60 / self.tempo_bpm * 1_000_000
        phrase = self.phrases[number % len(self.phrases)]
        self._schedule += [PlayedNote(start_us + round(b * spb), p) for b, p in phrase]

    def next_event_us(self, clock) -> int | None:
        return self._schedule[0].t_us if self._schedule else None

    def poll(self, clock) -> list[PlayedNote]:
        due = [n for n in self._schedule if n.t_us <= clock.now_us()]
        self._schedule = self._schedule[len(due) :]
        self.played += due
        return due
