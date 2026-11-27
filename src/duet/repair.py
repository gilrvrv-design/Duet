"""Deterministic repair of the robot part (spec §5.2 FR-S4).

Steps, in order:
1. octave-fold notes with no bottle onto one (or the nearest bottle);
2. keep only the highest of notes that start together;
3. push a too-fast note later to the next grid point, if that is a small move;
   otherwise drop it;
4. drop notes that break the solenoid duty limit;
5. if too many notes were dropped, slow the tempo instead and start again.

Every change is logged so the user (or the LLM) can see what happened.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from duet.feasibility import DEFAULT_MARGIN_S, Code, check_robot, robot_strikes
from duet.kinematics import reachability
from duet.pitch import midi_to_name
from duet.profile import RobotProfile
from duet.score import DuetScore, Event
from duet.timing import bar_and_beat, beat_index, seconds_per_beat

GRID_BEATS = 0.25
MAX_SHIFT_BEATS = 0.5
MAX_DROP_RATIO = 0.2
MIN_TEMPO_BPM = 40.0


@dataclass(frozen=True)
class Change:
    kind: str  # "fold", "drop", "shift", "tempo"
    bar: int
    beat: float
    detail: str


@dataclass
class RepairResult:
    score: DuetScore
    changes: list[Change] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(c.kind == kind for c in self.changes)

    def summary(self) -> str:
        return "\n".join(f"{c.kind}: bar {c.bar} beat {c.beat:g}: {c.detail}" for c in self.changes)


def repair_robot(
    score: DuetScore,
    profile: RobotProfile,
    margin_s: float = DEFAULT_MARGIN_S,
    keep_tempo: bool = False,
) -> RepairResult:
    """``keep_tempo``: never slow down (for live sessions); drop or shift notes instead."""
    robot_notes = sum(e.part == "robot" for e in score.events)
    result = _repair_once(score, profile, margin_s)
    too_many_dropped = robot_notes and result.count("drop") / robot_notes > MAX_DROP_RATIO
    if too_many_dropped and not keep_tempo:
        slower = _slower_tempo(score, profile, margin_s)
        if slower is not None and slower < score.meta.tempo_bpm:
            retry = _repair_once(score.with_tempo(slower), profile, margin_s)
            if retry.count("drop") < result.count("drop"):
                retry.changes.insert(
                    0,
                    Change(
                        "tempo",
                        1,
                        1.0,
                        f"tempo lowered from {score.meta.tempo_bpm:g} to {slower:g} bpm",
                    ),
                )
                result = retry
    final = check_robot(result.score, profile, margin_s)
    if not final.ok:  # a bug, not a user error: repair must always succeed
        raise AssertionError(f"repair left violations:\n{final.feedback()}")
    return result


def _repair_once(score: DuetScore, profile: RobotProfile, margin_s: float) -> RepairResult:
    changes: list[Change] = []
    events = list(score.events)
    events = _fold(events, profile, changes)
    score = score.with_events(events)
    score = _fix_timing(score, profile, margin_s, changes)
    score = _fix_duty(score, profile, margin_s, changes)
    return RepairResult(score, changes)


def _fold(events: list[Event], profile: RobotProfile, changes: list[Change]) -> list[Event]:
    out = []
    for event in events:
        if event.part != "robot" or profile.bottle_index(event.pitch) is not None:
            out.append(event)
            continue
        target = _fold_pitch(event.pitch, profile.pitches)
        changes.append(
            Change(
                "fold",
                event.bar,
                event.beat,
                f"{midi_to_name(event.pitch)} -> {midi_to_name(target)}",
            )
        )
        out.append(event.model_copy(update={"pitch": target}))
    return out


def _fold_pitch(pitch: int, available: list[int]) -> int:
    """Same pitch class in the nearest octave if a bottle has it, else the nearest bottle."""
    same_class = [p for p in available if p % 12 == pitch % 12]
    pool = same_class or available
    return min(pool, key=lambda p: (abs(p - pitch), p))


def _fix_timing(
    score: DuetScore, profile: RobotProfile, margin_s: float, changes: list[Change]
) -> DuetScore:
    spb = seconds_per_beat(score.meta.tempo_bpm)
    per_bar = score.meta.beats_per_bar
    matrix = reachability(profile)
    strikes, _ = robot_strikes(score, profile)
    # Among simultaneous notes, play the highest (usually the melody) first.
    strikes.sort(key=lambda s: (s.time_s, -score.events[s.index].pitch))

    events = list(score.events)
    dropped: set[int] = set()
    prev = None  # (bottle, time_s)
    for strike in strikes:
        event = events[strike.index]
        if prev is None:
            prev = (strike.bottle, strike.time_s)
            continue
        earliest = prev[1] + matrix.min_interval(prev[0], strike.bottle) + margin_s
        if strike.time_s >= earliest - 1e-9:
            prev = (strike.bottle, strike.time_s)
            continue
        start_beats = beat_index(event.bar, event.beat, per_bar)
        new_beats = math.ceil(earliest / spb / GRID_BEATS - 1e-9) * GRID_BEATS
        shift = new_beats - start_beats
        if strike.time_s > prev[1] + 1e-9 and shift <= MAX_SHIFT_BEATS + 1e-9:
            bar, beat = bar_and_beat(new_beats, per_bar)
            dur = max(GRID_BEATS, event.dur - shift)
            changes.append(
                Change(
                    "shift",
                    event.bar,
                    event.beat,
                    f"{midi_to_name(event.pitch)} moved {shift:g} beat later",
                )
            )
            events[strike.index] = event.model_copy(update={"bar": bar, "beat": beat, "dur": dur})
            prev = (strike.bottle, new_beats * spb)
        else:
            reason = "plays with another note" if strike.time_s <= prev[1] + 1e-9 else "too fast"
            changes.append(
                Change("drop", event.bar, event.beat, f"{midi_to_name(event.pitch)} {reason}")
            )
            dropped.add(strike.index)
    return score.with_events([e for i, e in enumerate(events) if i not in dropped])


def _fix_duty(
    score: DuetScore, profile: RobotProfile, margin_s: float, changes: list[Change]
) -> DuetScore:
    report = check_robot(score, profile, margin_s)
    drop = {v.event_index for v in report.violations if v.code == Code.DUTY_CYCLE}
    for i in sorted(drop):
        event = score.events[i]
        changes.append(
            Change("drop", event.bar, event.beat, f"{midi_to_name(event.pitch)} duty cycle")
        )
    return score.with_events([e for i, e in enumerate(score.events) if i not in drop])


def _slower_tempo(score: DuetScore, profile: RobotProfile, margin_s: float) -> float | None:
    """Tempo at which every robot gap is wide enough, rounded down to a whole bpm."""
    matrix = reachability(profile)
    strikes, _ = robot_strikes(score, profile)
    factor = 1.0
    for prev, cur in zip(strikes, strikes[1:], strict=False):
        gap = cur.time_s - prev.time_s
        if gap <= 1e-9:
            continue  # simultaneous notes are dropped whatever the tempo
        needed = matrix.min_interval(prev.bottle, cur.bottle) + margin_s
        factor = max(factor, needed / gap)
    if factor == 1.0:
        return None
    return max(MIN_TEMPO_BPM, math.floor(score.meta.tempo_bpm / factor))
