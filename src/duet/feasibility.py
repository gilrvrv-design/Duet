"""Can the robot play this score? (spec §5.2 FR-S3)

Returns structured violations. The same list feeds deterministic repair and the
feedback sent back to the LLM.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from duet.kinematics import reachability
from duet.pitch import midi_to_name
from duet.profile import RobotProfile
from duet.score import DuetScore
from duet.timing import beat_index, seconds_per_beat

DEFAULT_MARGIN_S = 0.010


class Code(StrEnum):
    NOT_ON_BOTTLE = "NOT_ON_BOTTLE"
    SIMULTANEOUS = "SIMULTANEOUS"
    TOO_FAST = "TOO_FAST"
    DUTY_CYCLE = "DUTY_CYCLE"


@dataclass(frozen=True)
class Violation:
    code: Code
    event_index: int
    bar: int
    beat: float
    message: str
    needed_s: float | None = None
    available_s: float | None = None

    @property
    def shortfall_s(self) -> float:
        if self.needed_s is None or self.available_s is None:
            return 0.0
        return self.needed_s - self.available_s


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def codes(self) -> list[Code]:
        return [v.code for v in self.violations]

    def feedback(self) -> str:
        """One line per problem, worded for a composer (human or LLM)."""
        return "\n".join(f"bar {v.bar} beat {v.beat:g}: {v.message}" for v in self.violations)


@dataclass(frozen=True)
class _Strike:
    index: int
    bottle: int
    time_s: float
    bar: int
    beat: float
    vel: int


def robot_strikes(score: DuetScore, profile: RobotProfile, tolerance_cents: float = 50.0):
    """Map robot events to bottles. Returns (strikes sorted by time, unmapped event indices)."""
    spb = seconds_per_beat(score.meta.tempo_bpm)
    per_bar = score.meta.beats_per_bar
    strikes, unmapped = [], []
    for i, event in enumerate(score.events):
        if event.part != "robot":
            continue
        bottle = profile.bottle_index(event.pitch, tolerance_cents)
        if bottle is None:
            unmapped.append(i)
            continue
        t = beat_index(event.bar, event.beat, per_bar) * spb
        strikes.append(_Strike(i, bottle, t, event.bar, event.beat, event.vel))
    strikes.sort(key=lambda s: (s.time_s, s.index))
    return strikes, unmapped


def check_robot(
    score: DuetScore,
    profile: RobotProfile,
    margin_s: float = DEFAULT_MARGIN_S,
    tolerance_cents: float = 50.0,
) -> Report:
    report = Report()
    strikes, unmapped = robot_strikes(score, profile, tolerance_cents)
    available = ", ".join(midi_to_name(p) for p in profile.pitches)

    for i in unmapped:
        event = score.events[i]
        report.violations.append(
            Violation(
                Code.NOT_ON_BOTTLE,
                i,
                event.bar,
                event.beat,
                f"robot has no bottle for {midi_to_name(event.pitch)} (bottles: {available})",
            )
        )

    matrix = reachability(profile)
    for prev, cur in zip(strikes, strikes[1:], strict=False):
        gap = cur.time_s - prev.time_s
        target = midi_to_name(profile.pitches[cur.bottle])
        if gap <= 1e-9:
            report.violations.append(
                Violation(
                    Code.SIMULTANEOUS,
                    cur.index,
                    cur.bar,
                    cur.beat,
                    f"robot can only play one note at a time; {target} starts with another note",
                    needed_s=matrix.min_interval(prev.bottle, cur.bottle) + margin_s,
                    available_s=0.0,
                )
            )
            continue
        needed = matrix.min_interval(prev.bottle, cur.bottle) + margin_s
        if gap < needed:
            source = midi_to_name(profile.pitches[prev.bottle])
            report.violations.append(
                Violation(
                    Code.TOO_FAST,
                    cur.index,
                    cur.bar,
                    cur.beat,
                    f"robot needs {needed:.2f} s to go from {source} to {target} "
                    f"but has {gap:.2f} s",
                    needed_s=needed,
                    available_s=gap,
                )
            )

    report.violations.extend(_check_duty(strikes, profile))
    report.violations.sort(key=lambda v: (v.bar, v.beat, v.code))
    return report


def _check_duty(strikes: list[_Strike], profile: RobotProfile) -> list[Violation]:
    """Solenoid on-time over any window must stay under the duty limit (FR-R6)."""
    window_s = profile.striker.duty_window_s
    limit = profile.striker.duty_limit * window_s
    window: deque[tuple[float, float]] = deque()
    on_time = 0.0
    found = []
    for strike in strikes:
        pulse = profile.striker.pulse_for_velocity(strike.vel) / 1_000_000
        window.append((strike.time_s, pulse))
        on_time += pulse
        while window and window[0][0] <= strike.time_s - window_s:
            on_time -= window.popleft()[1]
        if on_time > limit + 1e-12:
            found.append(
                Violation(
                    Code.DUTY_CYCLE,
                    strike.index,
                    strike.bar,
                    strike.beat,
                    f"too many robot notes in {window_s:g} s: solenoid would be on {on_time:.2f} s "
                    f"(limit {limit:.2f} s)",
                )
            )
            on_time -= window.pop()[1]  # count as if this strike were dropped
    return found
