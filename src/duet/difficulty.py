"""How hard is the pianist part? (spec §5.2 FR-S5)

Each level has plain rules. A part's difficulty is the lowest level whose rules it
meets, so the score is easy to explain ("level 3 because it has a 6-note jump").
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from duet.pitch import is_black_key, midi_to_name
from duet.profile import KeyboardProfile
from duet.score import MAX_LEVEL, MIN_LEVEL, DuetScore
from duet.timing import EPSILON, onset_groups, polyphony, timed_events


@dataclass(frozen=True)
class LevelRules:
    level: int
    max_notes_per_s: float
    max_jump: int  # semitones between consecutive onsets
    max_polyphony: int
    offbeats: bool  # onsets between beats
    black_keys: bool


LEVELS = (
    LevelRules(1, 1.0, 4, 1, offbeats=False, black_keys=False),
    LevelRules(2, 1.5, 5, 1, offbeats=True, black_keys=False),
    LevelRules(3, 2.5, 7, 2, offbeats=True, black_keys=True),
    LevelRules(4, 4.0, 12, 3, offbeats=True, black_keys=True),
    LevelRules(5, 1e9, 127, 10, offbeats=True, black_keys=True),
)
assert [r.level for r in LEVELS] == list(range(MIN_LEVEL, MAX_LEVEL + 1))


def rules_for(level: int) -> LevelRules:
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise ValueError(f"difficulty level {level} is outside {MIN_LEVEL}..{MAX_LEVEL}")
    return LEVELS[level - MIN_LEVEL]


def clamp_level(level: int) -> int:
    return max(MIN_LEVEL, min(MAX_LEVEL, level))


@dataclass(frozen=True)
class PartStats:
    notes: int
    notes_per_s: float
    max_jump: int
    max_polyphony: int
    has_offbeats: bool
    has_black_keys: bool
    low: int | None
    high: int | None


def pianist_stats(score: DuetScore) -> PartStats:
    timed = timed_events(score, "pianist")
    if not timed:
        return PartStats(0, 0.0, 0, 0, False, False, None, None)
    groups = onset_groups(timed)
    # Speed between notes: what makes a part hard. One note has no speed.
    span = groups[-1][0].start_s - groups[0][0].start_s
    tops = [max(t.event.pitch for t in group) for group in groups]
    pitches = [t.event.pitch for t in timed]
    return PartStats(
        notes=len(groups),
        notes_per_s=(len(groups) - 1) / span if span > 0 else 0.0,
        max_jump=max((abs(b - a) for a, b in pairwise(tops)), default=0),
        max_polyphony=polyphony(timed),
        has_offbeats=any(abs(t.event.beat - round(t.event.beat)) > EPSILON for t in timed),
        has_black_keys=any(is_black_key(p) for p in pitches),
        low=min(pitches),
        high=max(pitches),
    )


def broken_rules(stats: PartStats, rules: LevelRules) -> list[str]:
    problems = []
    if stats.notes_per_s > rules.max_notes_per_s + EPSILON:
        problems.append(f"{stats.notes_per_s:.1f} notes per second (max {rules.max_notes_per_s:g})")
    if stats.max_jump > rules.max_jump:
        problems.append(f"a jump of {stats.max_jump} semitones (max {rules.max_jump})")
    if stats.max_polyphony > rules.max_polyphony:
        problems.append(f"{stats.max_polyphony} notes at once (max {rules.max_polyphony})")
    if stats.has_offbeats and not rules.offbeats:
        problems.append("notes between beats")
    if stats.has_black_keys and not rules.black_keys:
        problems.append("black keys")
    return problems


def pianist_difficulty(score: DuetScore) -> int:
    stats = pianist_stats(score)
    # A part beyond even the top level's rules (say, 11 notes at once) is top level.
    return next((r.level for r in LEVELS if not broken_rules(stats, r)), MAX_LEVEL)


def check_pianist(
    score: DuetScore, keyboard: KeyboardProfile, target_level: int | None = None
) -> list[str]:
    """Problems with the pianist part: keys off the keyboard or outside the part's range,
    and rules above the target level."""
    problems = []
    part_range = score.parts["pianist"].range
    for e in score.part_events("pianist"):
        where = f"bar {e.bar} beat {e.beat:g}"
        if not keyboard.contains(e.pitch):
            problems.append(f"{where}: {midi_to_name(e.pitch)} is not on the keyboard")
        elif part_range and not part_range[0] <= e.pitch <= part_range[1]:
            low, high = (midi_to_name(p) for p in part_range)
            problems.append(f"{where}: {midi_to_name(e.pitch)} is outside {low}-{high}")
    level = target_level or score.meta.difficulty_target
    if level:
        rules = rules_for(level)
        problems += [
            f"too hard for level {level}: {p}" for p in broken_rules(pianist_stats(score), rules)
        ]
    return problems
