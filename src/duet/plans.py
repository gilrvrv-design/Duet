"""Compile a checked score into timed plans for the two players (spec FR-S6, §5.3, §5.4).

All times are seconds from the first beat of bar 1. Count-in cues have negative times.
"""

from __future__ import annotations

from dataclasses import dataclass

from duet.feasibility import check_robot, robot_strikes
from duet.kinematics import move_time_s
from duet.pitch import is_black_key
from duet.profile import KeyboardProfile, RobotProfile
from duet.score import DuetScore
from duet.timing import seconds_per_beat, timed_events

HOME_STEPS = 0

Color = tuple[int, int, int]
PRE_CUE: Color = (40, 40, 40)
PLAY_NOW: Color = (255, 255, 255)
COUNT_IN: Color = (0, 80, 255)


class InfeasibleScoreError(ValueError):
    pass


@dataclass(frozen=True)
class RobotCommand:
    sound_s: float  # when the bottle should be heard
    bar: int  # the score's bar of the note
    fire_s: float  # when to pulse the solenoid (sound time minus latency)
    bottle: int
    target_steps: int
    pulse_us: int
    move_start_s: float  # when the carriage leaves for this bottle
    move_s: float  # travel and settle time (0 if it is already there)


@dataclass(frozen=True)
class RobotPlan:
    commands: tuple[RobotCommand, ...]
    preroll_s: float  # time needed before bar 1 to reach the first bottle from home


def robot_plan(
    score: DuetScore, profile: RobotProfile, start_steps: int = HOME_STEPS, *, part: str
) -> RobotPlan:
    """The carriage-striker's commands for a bot's ``part``. ``start_steps``: where the
    carriage is now (home, or where the last piece ended)."""
    report = check_robot(score, profile, part=part)
    if not report.ok:
        raise InfeasibleScoreError(report.feedback())
    strikes, _ = robot_strikes(score, profile, part=part)
    latency = profile.striker.latency_ms / 1000
    commands = []
    position = start_steps
    for strike in strikes:
        target = profile.notes[strike.bottle].steps
        move = move_time_s(position, target, profile.kinematics)
        fire = strike.time_s - latency
        commands.append(
            RobotCommand(
                sound_s=strike.time_s,
                bar=strike.bar,
                fire_s=fire,
                bottle=strike.bottle,
                target_steps=target,
                pulse_us=profile.striker.pulse_for_velocity(strike.vel),
                move_start_s=fire - move,  # just in time: wait at the last bottle while it rings
                move_s=move,
            )
        )
        position = target
    preroll = max(0.0, -commands[0].move_start_s) if commands else 0.0
    return RobotPlan(tuple(commands), preroll)


def led_span(midi: int, keyboard: KeyboardProfile) -> tuple[int, int]:
    """(first LED, count) of the LEDs above a key.

    Uses ~1/12 of an octave around the key centre, which gives about two LEDs per
    semitone on a 144/m strip.
    """
    if not keyboard.contains(midi):
        raise ValueError(f"key {midi} is not on the keyboard")
    w = keyboard.led.white_key_mm
    whites_below = sum(1 for m in range(keyboard.low, midi) if not is_black_key(m))
    centre = whites_below * w if is_black_key(midi) else (whites_below + 0.5) * w
    half = 7 * w / 12 / 2
    pitch_mm = 1000 / keyboard.led.leds_per_m
    first = round((centre - half - keyboard.led.first_led_mm) / pitch_mm + 0.5)
    last = round((centre + half - keyboard.led.first_led_mm) / pitch_mm - 0.5)
    return max(first, 0), max(1, last - first + 1)


def led_count(keyboard: KeyboardProfile) -> int:
    whites = sum(1 for m in range(keyboard.low, keyboard.high + 1) if not is_black_key(m))
    length = whites * keyboard.led.white_key_mm - keyboard.led.first_led_mm
    return round(length * keyboard.led.leds_per_m / 1000)


@dataclass(frozen=True)
class LedCue:
    on_s: float
    off_s: float
    first_led: int
    count: int
    color: Color
    kind: str  # "pre", "now", "count_in"


def led_plan(
    score: DuetScore,
    keyboard: KeyboardProfile,
    lead_beats: float = 1.0,
    count_in_bars: int = 1,
    *,
    part: str,
) -> list[LedCue]:
    """The light cues guiding a human through ``part`` on a keyboard, after a count-in."""
    spb = seconds_per_beat(score.meta.tempo_bpm)
    cues = []
    total = led_count(keyboard)
    beats = score.meta.beats_per_bar * count_in_bars
    for i in range(beats):
        on = (i - beats) * spb
        cues.append(LedCue(on, on + spb / 2, 0, total, COUNT_IN, "count_in"))
    for t in timed_events(score, part):
        first, count = led_span(t.event.pitch, keyboard)
        pre_on = max(t.start_s - lead_beats * spb, -beats * spb)
        if pre_on < t.start_s:
            cues.append(LedCue(pre_on, t.start_s, first, count, PRE_CUE, "pre"))
        cues.append(LedCue(t.start_s, t.end_s, first, count, PLAY_NOW, "now"))
    return sorted(cues, key=lambda c: (c.on_s, c.first_led))
