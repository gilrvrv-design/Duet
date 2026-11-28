"""Variations of a duet (spec §5.1 FR-C8): "slower", "easier", "swap"... as edits.

Simple, common edits are done in code: instant, free and predictable. Anything else
goes to the composer as an edit of the current duet (``duet.compose.service.revise``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from duet.difficulty import COMFORTABLE_RANGE, clamp_level, pianist_stats, rules_for
from duet.feasibility import max_speed_up
from duet.performers import Bot, human_difficulty, in_use, performer, performers
from duet.pitch import best_transpose, is_black_key
from duet.profile import KeyboardProfile, RobotProfile, keyboard_profile, robot_profile
from duet.score import DuetScore, Event, clamp_tempo

if TYPE_CHECKING:
    from duet.compose.service import CompositionResult

Edit = Callable[..., "CompositionResult"]  # see vary
SLOWER, FASTER = 0.85, 1.15  # tempo factors of one "slower" or "faster" step
BUILT_IN = ("slower", "faster", "easier", "swap")


class VariationError(ValueError):
    """The variation cannot be made as asked."""


def is_built_in(instruction: str) -> bool:
    """Built-in variations run in code; anything else needs the composer."""
    return instruction.strip().lower() in BUILT_IN


def change_tempo(score: DuetScore, factor: float, bots: list[Bot]) -> DuetScore:
    """Scale the tempo; when speeding up, never beyond what every moving bot can play."""
    if factor > 1:
        for bot in (b for b in bots if b.moves):
            factor = min(factor, max_speed_up(score, bot.profile, part=bot.part))
        tempo = math.floor(score.meta.tempo_bpm * factor * 10) / 10  # round toward safe
    else:
        tempo = round(score.meta.tempo_bpm * factor, 1)
    return score.with_tempo(clamp_tempo(tempo))


def simplify_part(score: DuetScore, part: str, target_level: int) -> DuetScore:
    """Make a human's ``part`` fit ``target_level`` using that level's own rules: chords
    shrink to their top notes, offbeats move to the beat, black keys become the white key
    below, jumps shrink (nearest octave, then the nearest allowed key in the same
    direction, inside the part's range), and dense passages keep their strong beats."""
    rules = rules_for(target_level)
    low, high = score.parts[part].range or COMFORTABLE_RANGE
    events = sorted(score.part_events(part), key=lambda e: (e.bar, e.beat, -e.pitch))
    others = [e for e in score.events if e.part != part]

    # Order matters: thinning removes notes, which can make jumps bigger, so jumps go last.
    events = _limit_chords(events, rules.max_polyphony)
    if not rules.offbeats:
        events = _onto_beats(events)
    half = 1 + score.meta.beats_per_bar / 2
    keepers = [  # thinner and thinner: strong beats, then downbeats, then every other bar
        lambda e: e.beat in (1.0, half),
        lambda e: e.beat == 1.0,
        lambda e: e.beat == 1.0 and e.bar % 2 == 1,
    ]
    for keep in keepers:
        if (
            pianist_stats(score.with_events(others + events), part=part).notes_per_s
            <= rules.max_notes_per_s
        ):
            break
        events = [e for e in events if keep(e)] or events[:1]
    events = _shrink_jumps(events, rules.max_jump, low, high, rules.black_keys)
    return score.with_events(others + events)


def _limit_chords(events: list[Event], keep: int) -> list[Event]:
    """At most ``keep`` notes at once: the highest ones (events come highest first)."""
    count: dict[tuple, int] = {}
    out = []
    for e in events:
        at = (e.bar, e.beat)
        if count.get(at, 0) < keep:
            count[at] = count.get(at, 0) + 1
            out.append(e)
    return out


def _onto_beats(events: list[Event]) -> list[Event]:
    taken, out = set(), []
    for e in events:
        beat = float(int(e.beat))
        if (e.bar, beat) in taken:
            continue  # two notes would land on the same beat: keep the first
        taken.add((e.bar, beat))
        out.append(e.revised({"beat": beat, "dur": max(1.0, e.dur)}))
    return out


def _shrink_jumps(events, max_jump: int, low: int, high: int, black_ok: bool) -> list[Event]:
    """Jumps are measured between the top notes of consecutive onsets, so each onset (a
    chord moves as one) is shifted to bring its top note near the previous top."""
    groups: dict[tuple, list[Event]] = {}
    for e in events:
        groups.setdefault((e.bar, e.beat), []).append(e)
    out: list[Event] = []
    prev_top = None
    for key in sorted(groups):
        group = groups[key]
        top = max(e.pitch for e in group)
        bottom = min(e.pitch for e in group)
        shifts = [k for k in range(-48, 49, 12) if low <= bottom + k and top + k <= high] or [0]
        if prev_top is None:
            middle = (low + high) / 2
            shift = min(shifts, key=lambda k: abs(top + k - middle))
        else:
            shift = min(shifts, key=lambda k: (abs(top + k - prev_top), k))
            new_top = top + shift
            if abs(new_top - prev_top) > max_jump:  # still too far: nearest allowed key that way
                step = 1 if new_top > prev_top else -1
                allowed = [
                    prev_top + step * d
                    for d in range(max_jump, -1, -1)
                    if low <= prev_top + step * d <= high
                    and (black_ok or not is_black_key(prev_top + step * d))
                ]
                if allowed:
                    shift = allowed[0] - top
        for e in group:
            pitch = min(high, max(low, e.pitch + shift))
            if not black_ok and is_black_key(pitch):  # the white key on the side of the last note
                pitch = pitch - 1 if prev_top is None or pitch > prev_top else pitch + 1
            out.append(e.revised({"pitch": pitch}))
        prev_top = max(e.pitch for e in out[-len(group) :])
    return out


def swap_parts(score: DuetScore, bot: Bot, keyboard: KeyboardProfile) -> DuetScore:
    """In a duet, the bot takes the human's notes and the human takes the bot's, each
    moved to where its instrument can play them."""
    human = score.part_played_by("human")
    old_human = score.part_events(human)
    old_bot = score.part_events(bot.part)
    shift_bot = best_transpose([e.pitch for e in old_human], bot.instrument.pitches)
    low, high = score.parts[human].range or (keyboard.low, keyboard.high)
    middle = (low + high) / 2
    melody = [e.pitch for e in old_bot] or [middle]
    shift_human = 12 * round((middle - sum(melody) / len(melody)) / 12)
    events = [e.revised({"part": bot.part, "pitch": e.pitch + shift_bot}) for e in old_human]
    events += [e.revised({"part": human, "pitch": e.pitch + shift_human}) for e in old_bot]
    return bot.repair(score.with_events(events)).score


def vary(
    score: DuetScore,
    instruction: str,
    edit: Edit | None = None,
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
) -> tuple[DuetScore, str]:
    """Apply a variation. Returns (new score, what was done).

    ``edit`` handles what is not built in, usually ``revise`` bound to a composer and a
    copyright guard; it is called with the score, the instruction and keyword arguments
    ``robot``, ``keyboard`` and ``difficulty``."""
    robot = robot or robot_profile()
    keyboard = keyboard or keyboard_profile()
    playing = in_use(robot, keyboard)
    bots = [p for p in performers(score, playing) if isinstance(p, Bot)]
    word = instruction.strip().lower()  # see is_built_in
    if word == "slower":
        new = change_tempo(score, SLOWER, bots)
        return new, f"tempo {score.meta.tempo_bpm:g} -> {new.meta.tempo_bpm:g} bpm"
    if word == "faster":
        new = change_tempo(score, FASTER, bots)
        return new, f"tempo {score.meta.tempo_bpm:g} -> {new.meta.tempo_bpm:g} bpm"
    if word == "easier":
        before = human_difficulty(score)
        target = clamp_level(before - 1)
        new = score
        for part in score.parts_played_by("human"):
            new = simplify_part(new, part, target)
        new = new.revised({"meta": new.meta.revised({"difficulty_target": target})})
        return new, f"level {before} -> {human_difficulty(new)}"
    if word == "swap":
        bot = performer(score, score.part_played_by("bot"), playing)
        human = score.part_played_by("human")
        return swap_parts(score, bot, keyboard), f"{bot.part} and {human} swapped parts"
    if edit is None:
        raise VariationError(
            f"{instruction!r} needs the composer (built in: {', '.join(BUILT_IN)})"
        )
    target = None
    if word == "harder":
        target = clamp_level(human_difficulty(score) + 1)
        instruction = f"make the human part a little harder (level {target})"
    result = edit(score, instruction, robot=robot, keyboard=keyboard, difficulty=target)
    unplayable = [b.part for b in bots if b.problems(result.score)]
    if unplayable:
        raise VariationError(f"the edited duet is not playable by the bot: {unplayable}")
    return result.score, result.explanation or instruction
