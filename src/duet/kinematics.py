"""Carriage motion (spec §5.3 FR-R1): how long the striker needs between two bottles.

The carriage follows a trapezoidal (or, for short moves, triangular) speed profile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from duet.pitch import midi_to_name
from duet.profile import Kinematics, RobotProfile


def travel_time_s(distance_mm: float, v_max: float, a_max: float) -> float:
    """Time to move ``distance_mm`` from rest to rest."""
    distance_mm = abs(distance_mm)
    if distance_mm == 0:
        return 0.0
    if distance_mm <= v_max**2 / a_max:  # never reaches top speed
        return 2.0 * math.sqrt(distance_mm / a_max)
    return distance_mm / v_max + v_max / a_max


def move_time_s(from_steps: int, to_steps: int, kin: Kinematics) -> float:
    """Travel plus settle time between two carriage positions (0 if they are the same)."""
    if from_steps == to_steps:
        return 0.0
    distance = (to_steps - from_steps) / kin.steps_per_mm
    return travel_time_s(distance, kin.v_max_mm_s, kin.a_max_mm_s2) + kin.settle_ms / 1000


@dataclass(frozen=True)
class Reachability:
    """Minimum time between consecutive strikes for every pair of bottles."""

    pitches: tuple[int, ...]
    seconds: tuple[tuple[float, ...], ...]

    def min_interval(self, i: int, j: int) -> float:
        return self.seconds[i][j]

    def as_table(self) -> str:
        """Plain-text table in milliseconds, for LLM prompts and humans."""
        names = [midi_to_name(p) for p in self.pitches]
        lines = ["from\\to " + " ".join(f"{n:>5}" for n in names)]
        for name, row in zip(names, self.seconds, strict=True):
            lines.append(f"{name:>7} " + " ".join(f"{round(s * 1000):>5}" for s in row))
        return "\n".join(lines)


def strike_interval_s(profile: RobotProfile, i: int, j: int) -> float:
    """Minimum time from a strike on bottle ``i`` to a strike on bottle ``j``.

    The striker must finish its pulse before the carriage moves; a repeat on the
    same bottle needs the solenoid recovery time.
    """
    pulse = profile.striker.pulse_us[1] / 1_000_000
    recovery = profile.striker.recovery_ms / 1000
    if i == j:
        return max(recovery, pulse)
    move = move_time_s(profile.notes[i].steps, profile.notes[j].steps, profile.kinematics)
    return max(recovery, pulse + move)


def reachability(profile: RobotProfile) -> Reachability:
    n = len(profile.notes)
    rows = tuple(tuple(strike_interval_s(profile, i, j) for j in range(n)) for i in range(n))
    return Reachability(tuple(profile.pitches), rows)
