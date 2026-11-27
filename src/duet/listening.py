"""Hearing the pianist (spec §5.6): key input, wait-mode gates and hit grading.

Key input comes from a MIDI keyboard (``MidiKeys``) or, for demos and tests, a
simulated pianist (``SimulatedPianist``). Both record what was played so the
performance can be graded afterwards (FR-H4, FR-E4).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class PlayedNote:
    t_us: int
    pitch: int
    velocity: int = 80


class Clock(Protocol):
    def now_us(self) -> int: ...
    def sleep_until(self, t_us: int) -> None: ...


class KeyInput(Protocol):
    played: list[PlayedNote]

    def wait_for(self, pitches: frozenset[int], since_us: int, clock: Clock) -> int:
        """Wait mode: block until every pitch was pressed at or after ``since_us``."""
        ...

    def poll(self, clock: Clock) -> list[PlayedNote]:
        """Follow mode: notes played since the last poll."""
        ...

    def next_event_us(self, clock: Clock) -> int | None:
        """Follow mode: when to poll next (None: nothing expected)."""
        ...


@dataclass
class SimulatedPianist:
    """Presses the right keys ``reaction_s`` after each cue. ``wrong_first`` makes it hit a
    neighbouring key first at those cue numbers, to exercise wrong-note handling."""

    reaction_s: float = 0.3
    wrong_first: set[int] = field(default_factory=set)
    played: list[PlayedNote] = field(default_factory=list)
    _cues: int = 0

    def wait_for(self, pitches, since_us, clock) -> int:
        cue = clock.now_us()
        if self._cues in self.wrong_first:
            self.played.append(PlayedNote(cue + 100_000, min(pitches) + 1))
        self._cues += 1
        press = cue + round(self.reaction_s * 1_000_000)
        clock.sleep_until(press)
        self.played += [PlayedNote(press, p) for p in sorted(pitches)]
        return press


class MidiPort(Protocol):
    def iter_pending(self) -> Iterable: ...


@dataclass
class MidiKeys:
    """A MIDI keyboard (any mido input port). Use ``mido.open_input(name)`` for the port."""

    port: MidiPort
    timeout_s: float | None = None  # None: wait as long as it takes
    played: list[PlayedNote] = field(default_factory=list)

    def poll(self, clock: Clock) -> list[PlayedNote]:
        new = [
            PlayedNote(clock.now_us(), msg.note, msg.velocity)
            for msg in self.port.iter_pending()
            if msg.type == "note_on" and msg.velocity > 0
        ]
        self.played += new
        return new

    def next_event_us(self, clock: Clock) -> int:
        return clock.now_us() + MIDI_POLL_US

    def wait_for(self, pitches, since_us, clock) -> int:
        return wait_for_pitches(self, pitches, since_us, clock, self.timeout_s, MIDI_POLL_US)


MIDI_POLL_US = 2000


def wait_for_pitches(keys, pitches, since_us: int, clock, timeout_s: float | None, poll_us: int):
    """Poll ``keys`` until every pitch was played since ``since_us``; return when the last
    of them was. After ``timeout_s`` give up on the note and return the time now, so the
    music plays on. Waits on ``clock``, so a virtual clock never really sleeps."""
    deadline = None if timeout_s is None else clock.now_us() + round(timeout_s * 1_000_000)
    wanted = set(pitches)
    while True:
        keys.poll(clock)
        times: dict[int, int] = {}
        for note in keys.played:
            if note.t_us >= since_us and note.pitch in wanted:
                times.setdefault(note.pitch, note.t_us)
        if len(times) == len(wanted):
            return max(times.values())
        now = clock.now_us()
        if deadline is not None and now >= deadline:
            return now
        wake = now + poll_us
        clock.sleep_until(wake if deadline is None else min(wake, deadline))


# Grading --------------------------------------------------------------------

HIT_MS = 100
WINDOW_MS = 300


@dataclass(frozen=True)
class Expected:
    t_us: int
    pitch: int
    bar: int


@dataclass(frozen=True)
class Grade:
    expected: Expected
    result: str  # hit, early, late, wrong, missed
    offset_ms: float | None = None
    played_pitch: int | None = None


@dataclass
class Report:
    grades: list[Grade]
    extras: list[PlayedNote]

    def count(self, result: str) -> int:
        return sum(g.result == result for g in self.grades)

    @property
    def accuracy(self) -> float:
        """Share of notes with the right key at about the right time."""
        if not self.grades:
            return 1.0
        return sum(g.result in ("hit", "early", "late") for g in self.grades) / len(self.grades)

    @property
    def mean_offset_ms(self) -> float:
        offsets = [
            g.offset_ms for g in self.grades if g.offset_ms is not None and g.result != "wrong"
        ]
        return statistics.mean(offsets) if offsets else 0.0

    def hardest_bars(self, n: int = 2) -> list[int]:
        misses: dict[int, int] = {}
        for g in self.grades:
            if g.result in ("wrong", "missed"):
                misses[g.expected.bar] = misses.get(g.expected.bar, 0) + 1
        return [bar for bar, _ in sorted(misses.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    def feedback(self) -> str:
        """Plain words for the pianist (FR-E4)."""
        total = len(self.grades)
        good = round(self.accuracy * total)
        lines = [f"You played {good} of {total} notes right ({self.accuracy:.0%})."]
        hardest = self.hardest_bars()
        if hardest:
            bars = " and ".join(str(b) for b in hardest)
            lines.append(
                f"Hardest: bar {bars}. Try {'it' if len(hardest) == 1 else 'them'} slower."
            )
        offset = self.mean_offset_ms
        if abs(offset) >= 40:
            lines.append(
                f"You tend to play {abs(offset):.0f} ms {'late' if offset > 0 else 'early'}."
            )
        if self.extras:
            lines.append(f"{len(self.extras)} extra note(s).")
        return " ".join(lines)


def _closest(played, exp: Expected, limit_ms: float, same_pitch: bool) -> PlayedNote | None:
    pool = [
        p
        for p in played
        if abs(p.t_us - exp.t_us) <= limit_ms * 1000 and (p.pitch == exp.pitch) == same_pitch
    ]
    return min(pool, key=lambda p: abs(p.t_us - exp.t_us)) if pool else None


def grade(
    expected: list[Expected], played: list[PlayedNote], hit_ms=HIT_MS, window_ms=WINDOW_MS
) -> Report:
    """Match each expected note with what was played (spec FR-H4).

    The right key within ``hit_ms`` is a hit, within ``window_ms`` early or late. If no
    right key came but another key did within ``hit_ms``, it is a wrong note. Played notes
    left over are extras.
    """
    unused = sorted(played, key=lambda p: p.t_us)
    grades = []
    for exp in sorted(expected, key=lambda e: (e.t_us, e.pitch)):
        match = _closest(unused, exp, window_ms, same_pitch=True)
        if match is not None:
            offset = (match.t_us - exp.t_us) / 1000
            result = "hit" if abs(offset) <= hit_ms else ("early" if offset < 0 else "late")
            grades.append(Grade(exp, result, offset, match.pitch))
            unused.remove(match)
            continue
        wrong = _closest(unused, exp, hit_ms, same_pitch=False)
        if wrong is not None:
            grades.append(Grade(exp, "wrong", (wrong.t_us - exp.t_us) / 1000, wrong.pitch))
            unused.remove(wrong)
        else:
            grades.append(Grade(exp, "missed"))
    return Report(grades, unused)


def grade_take(score, played: list[PlayedNote]) -> Report:
    """Grade a recorded take of the pianist part at the score's tempo. Recordings start
    at any moment, so the first played note is lined up with the first expected one."""
    from duet.timing import timed_events

    expected = [
        Expected(round(t.start_s * 1e6), t.event.pitch, t.event.bar)
        for t in timed_events(score, "pianist")
    ]
    if played and expected:
        shift = expected[0].t_us - min(p.t_us for p in played)
        played = [PlayedNote(p.t_us + shift, p.pitch, p.velocity) for p in played]
    return grade(expected, played)
