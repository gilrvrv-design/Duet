"""Prompts for the composer. Built from the instrument profiles, so they never go stale."""

from __future__ import annotations

from duet.difficulty import LEVELS
from duet.kinematics import reachability
from duet.pitch import midi_to_name
from duet.profile import RobotProfile


def system_prompt(robot: RobotProfile) -> str:
    bottles = ", ".join(midi_to_name(p) for p in robot.pitches)
    return f"""You compose short duets for a robot and a human pianist who perform together live.

The robot plays one part on {len(robot.notes)} tuned glass bottles: {bottles}.
- It has one striker on a carriage, so it plays one note at a time. Never write two robot notes
  that start together.
- The striker must travel between bottles. The table gives the minimum time in milliseconds
  from one robot note to the next (rows: from, columns: to). Leave at least that much time,
  plus a little margin, between consecutive robot notes:
{reachability(robot).as_table()}
- Use only those bottle pitches for the robot. A bottle rings for about
  {robot.sound.decay_ms / 1000:g} s, so long robot notes are fine.

The pianist is usually a beginner who follows lights above the keys and does not read music.
- Write the pianist part in the range you are given, for one hand unless told otherwise.
- Keep it at or below the requested difficulty level.

Write music that sounds good: a clear melody, a sensible harmony between the two parts, a
shape with a beginning and an ending, and phrases that answer each other.

Positions: bars and beats are 1-based (bar 1 beat 1 is the first beat). "dur" is in beats.
Tempo counts beats of the time signature. Pitches use scientific notation (C4 is middle C).
Answer with the JSON object only."""


def difficulty_rules(level: int) -> str:
    rules = LEVELS[level - 1]
    parts = [
        f"at most {rules.max_notes_per_s:g} pianist notes per second"
        if rules.max_notes_per_s < 1e6
        else "any speed",
        f"jumps of at most {rules.max_jump} semitones between notes",
        f"at most {rules.max_polyphony} notes at once",
        "notes may start between beats" if rules.offbeats else "every note starts on a beat",
        "black keys allowed" if rules.black_keys else "white keys only",
    ]
    return f"Pianist difficulty level {level} of 5: " + "; ".join(parts) + "."


def request_message(
    prompt: str,
    *,
    difficulty: int,
    bars: int,
    lead: str,
    pianist_range: tuple[str, str],
    tempo_bpm: float | None,
    time_signature: tuple[int, int] | None,
    focus: str | None = None,
) -> str:
    lines = [
        f"Request: {prompt}",
        f"Length: {bars} bars.",
        f"Who leads with the melody: {lead}.",
        f"Pianist range: {pianist_range[0]} to {pianist_range[1]}.",
        difficulty_rules(difficulty),
    ]
    if tempo_bpm:
        lines.append(f"Tempo: {tempo_bpm:g} bpm.")
    if time_signature:
        lines.append(f"Time signature: {time_signature[0]}/{time_signature[1]}.")
    if focus:
        lines.append(
            f"Practice focus: include a few {focus} in the pianist part, but keep most of it "
            "comfortable (about 85% familiar, 15% new)."
        )
    return "\n".join(lines)


def feedback_message(problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        "The duet cannot be performed as written. Fix only these problems and keep "
        f"everything else the same, then answer with the full JSON object again:\n{listed}"
    )
