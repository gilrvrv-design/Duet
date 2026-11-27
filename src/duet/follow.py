"""Follow mode (spec §5.6 FR-H3, FR-H5): the robot keeps the pianist's tempo.

``Follower`` maps score time to clock time. Every pianist note that matches the next
expected note re-anchors the map at that moment (phase), and the tempo estimate is
updated from the last two matches, smoothed and limited (rate). Times are microseconds;
"score time" means the planned clock time at the score's own tempo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duet.feasibility import robot_strikes
from duet.kinematics import reachability
from duet.listening import Expected, PlayedNote
from duet.profile import RobotProfile
from duet.score import DuetScore

MATCH_WINDOW_US = 400_000  # a played note this close to the expected time can match
SMOOTHING = 0.5  # weight of the newest tempo measurement
MAX_SLOW_DOWN = 1.6  # rate = clock time per score time; > 1 is slower


def max_speed_up(score: DuetScore, robot: RobotProfile, margin_s: float = 0.010) -> float:
    """How much faster than written the robot part can go and still be playable."""
    strikes, _ = robot_strikes(score, robot)
    matrix = reachability(robot)
    slack = float("inf")
    for prev, cur in zip(strikes, strikes[1:], strict=False):
        gap = cur.time_s - prev.time_s
        if gap > 0:
            slack = min(slack, gap / (matrix.min_interval(prev.bottle, cur.bottle) + margin_s))
    return max(1.0, min(slack, 1.5))


@dataclass
class Follower:
    expected: list[Expected]  # in score time, sorted
    min_rate: float = 1 / 1.5  # fastest allowed (set from max_speed_up)
    max_rate: float = MAX_SLOW_DOWN
    rate: float = 1.0
    anchor_score_us: int = 0
    anchor_clock_us: int = 0
    position: int = 0  # index of the next expected note
    matches: list[tuple[int, int]] = field(default_factory=list)  # (score us, clock us)

    def __post_init__(self) -> None:
        self.expected = sorted(self.expected, key=lambda e: (e.t_us, e.pitch))

    def to_clock(self, score_us: int) -> int:
        return round(self.anchor_clock_us + (score_us - self.anchor_score_us) * self.rate)

    def hear(self, note: PlayedNote) -> bool:
        """Feed one played note. Returns True if it moved the follower."""
        for k in range(self.position, min(self.position + 3, len(self.expected))):
            exp = self.expected[k]
            due = self.to_clock(exp.t_us)
            close = abs(note.t_us - due) <= MATCH_WINDOW_US
            if close and (note.pitch == exp.pitch or k == self.position):
                self._match(k, note.t_us)
                return True
        return False

    def _match(self, k: int, clock_us: int) -> None:
        score_us = self.expected[k].t_us
        if self.matches and score_us > self.matches[-1][0]:
            last_score, last_clock = self.matches[-1]
            measured = (clock_us - last_clock) / (score_us - last_score)
            blended = (1 - SMOOTHING) * self.rate + SMOOTHING * measured
            self.rate = min(self.max_rate, max(self.min_rate, blended))
        self.matches.append((score_us, clock_us))
        self.anchor_score_us, self.anchor_clock_us = score_us, clock_us
        # Skip notes of the same chord and anything we jumped past.
        self.position = k + 1
        while self.position < len(self.expected) and self.expected[self.position].t_us == score_us:
            self.position += 1


@dataclass
class TempoPianist:
    """A simulated pianist who ignores the robot and plays at their own tempo:
    ``stretch`` 1.1 is 10% slower than written; ``accelerate`` changes it per note."""

    stretch: float = 1.0
    accelerate: float = 0.0
    played: list[PlayedNote] = field(default_factory=list)
    schedule: list[PlayedNote] = field(default_factory=list)

    def begin(self, expected: list[Expected]) -> None:
        """Called by the conductor when the performance starts."""
        notes = sorted(expected, key=lambda e: (e.t_us, e.pitch))
        if not notes:
            return
        clock, last, factor = notes[0].t_us, notes[0].t_us, self.stretch
        for e in notes:
            if e.t_us > last:
                factor *= 1 + self.accelerate
            clock += round((e.t_us - last) * factor)
            last = e.t_us
            self.schedule.append(PlayedNote(clock, e.pitch))

    def next_event_us(self, clock) -> int | None:
        return self.schedule[0].t_us if self.schedule else None

    def poll(self, clock) -> list[PlayedNote]:
        due = [n for n in self.schedule if n.t_us <= clock.now_us()]
        self.schedule = self.schedule[len(due) :]
        self.played += due
        return due
