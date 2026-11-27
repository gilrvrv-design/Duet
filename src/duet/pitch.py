"""Pitch maths: note names, MIDI numbers, frequencies and cents.

This is the only place that knows how pitch names map to numbers (DRY).
"""

from __future__ import annotations

import math
import re

A4_MIDI = 69
A4_HZ = 440.0

_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTALS = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NAME_RE = re.compile(r"^([A-Ga-g])(##|#|bb|b)?(-?\d+)$")


class PitchError(ValueError):
    """Raised when a pitch name or number is not valid."""


def name_to_midi(name: str) -> int:
    """Convert scientific pitch notation (``"C4"``, ``"F#5"``, ``"Bb3"``) to a MIDI number.

    C4 is middle C (MIDI 60).
    """
    match = _NAME_RE.match(name.strip())
    if not match:
        raise PitchError(f"not a pitch name: {name!r}")
    letter, accidental, octave = match.groups()
    midi = (int(octave) + 1) * 12 + _STEPS[letter.upper()] + _ACCIDENTALS[accidental or ""]
    if not 0 <= midi <= 127:
        raise PitchError(f"pitch out of MIDI range: {name!r}")
    return midi


def midi_to_name(midi: int) -> str:
    """Convert a MIDI number to a pitch name, spelled with sharps."""
    if not 0 <= midi <= 127:
        raise PitchError(f"MIDI number out of range: {midi}")
    return f"{_SHARP_NAMES[midi % 12]}{midi // 12 - 1}"


def to_midi(pitch: str | int) -> int:
    """Accept a pitch name or a MIDI number and return a MIDI number."""
    if isinstance(pitch, bool):
        raise PitchError(f"not a pitch: {pitch!r}")
    if isinstance(pitch, int):
        midi_to_name(pitch)  # range check
        return pitch
    return name_to_midi(pitch)


def midi_to_hz(midi: float) -> float:
    """Equal-tempered frequency of a (possibly fractional) MIDI number."""
    return A4_HZ * 2.0 ** ((midi - A4_MIDI) / 12.0)


def hz_to_midi(hz: float) -> float:
    """Fractional MIDI number for a frequency."""
    if hz <= 0:
        raise PitchError(f"frequency must be positive: {hz}")
    return A4_MIDI + 12.0 * math.log2(hz / A4_HZ)


def cents_between(hz_a: float, hz_b: float) -> float:
    """Signed distance from ``hz_a`` to ``hz_b`` in cents."""
    return 1200.0 * math.log2(hz_b / hz_a)


def is_black_key(midi: int) -> bool:
    return midi % 12 in (1, 3, 6, 8, 10)
