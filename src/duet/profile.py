"""How the planner, the conductor and the checks see an instrument: thin, read-only views
of a ``duet.instruments.Instrument``. The instrument holds every fact and every rule;
a view only presents them the way its users need.

``RobotProfile``: an instrument played by a carriage-striker bot (notes with their
carriage positions, kinematics, striker). ``KeyboardProfile``: a keyboard played by a
human who follows an LED strip.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from duet.instruments import (
    CalibrationInfo,
    CarriageStriker,
    Instrument,
    Kinematics,
    LedStrip,
    Sound,
    Striker,
    instrument,
    load_instrument_file,
    save_instrument_file,
)
from duet.pitch import cents_between, midi_to_hz

__all__ = [
    "Bottle",
    "CalibrationInfo",
    "KeyboardProfile",
    "Kinematics",
    "RobotProfile",
    "Sound",
    "Striker",
    "keyboard_profile",
    "load_profile",
    "load_profile_file",
    "robot_profile",
    "save_profile_file",
]


@dataclass(frozen=True)
class Bottle:
    """One note of a carriage-striker bot: what it sounds, and where the carriage stops."""

    name: int  # MIDI number
    hz: float
    steps: int

    @property
    def midi(self) -> int:
        return self.name


@dataclass(frozen=True)
class RobotProfile:
    instrument: Instrument

    def __post_init__(self) -> None:
        if not isinstance(self.instrument.bot, CarriageStriker):
            raise TypeError(f"{self.instrument.id} is not played by a carriage-striker bot")
        if self.instrument.sound is None:
            raise ValueError(f"{self.instrument.id}: a bot's instrument needs its sound")

    @property
    def id(self) -> str:
        return self.instrument.id

    @property
    def name(self) -> str:
        return self.instrument.name

    @property
    def kinematics(self) -> Kinematics:
        return self.instrument.bot.kinematics

    @property
    def striker(self) -> Striker:
        return self.instrument.bot.striker

    @property
    def sound(self) -> Sound:
        return self.instrument.sound

    @property
    def calibration(self) -> CalibrationInfo | None:
        return self.instrument.calibration

    @property
    def tolerance_cents(self) -> float:
        return self.instrument.tolerance_cents

    @cached_property
    def notes(self) -> tuple[Bottle, ...]:
        return tuple(
            Bottle(n.midi, n.sounding_hz, steps)
            for n, steps in zip(self.instrument.notes, self.instrument.bot.positions, strict=True)
        )

    @property
    def pitches(self) -> list[int]:
        return self.instrument.pitches

    def bottle_index(self, midi: int, tolerance_cents: float | None = None) -> int | None:
        """Index of the note that sounds ``midi`` within the tolerance (the instrument's
        unless given), using measured pitch."""
        if tolerance_cents is None:
            tolerance_cents = self.tolerance_cents
        target = midi_to_hz(midi)
        best = min(
            range(len(self.notes)), key=lambda i: abs(cents_between(target, self.notes[i].hz))
        )
        if abs(cents_between(target, self.notes[best].hz)) <= tolerance_cents:
            return best
        return None


@dataclass(frozen=True)
class KeyboardProfile:
    instrument: Instrument

    def __post_init__(self) -> None:
        inst = self.instrument
        if inst.range is None or inst.human is None or not isinstance(inst.human.guide, LedStrip):
            raise TypeError(f"{inst.id} is not a keyboard played by a human with an LED strip")

    @property
    def id(self) -> str:
        return self.instrument.id

    @property
    def low(self) -> int:
        return self.instrument.range[0]

    @property
    def high(self) -> int:
        return self.instrument.range[1]

    @property
    def led(self) -> LedStrip:
        return self.instrument.human.guide

    def contains(self, midi: int) -> bool:
        return self.low <= midi <= self.high


Profile = RobotProfile | KeyboardProfile


def _view(inst: Instrument) -> Profile:
    """A carriage-striker bot's instrument as a RobotProfile, else a keyboard."""
    if isinstance(inst.bot, CarriageStriker):
        return RobotProfile(inst)
    return KeyboardProfile(inst)


def load_profile_file(path: str | Path) -> Profile:
    return _view(load_instrument_file(path))


def save_profile_file(profile: Profile, path: str | Path) -> None:
    save_instrument_file(profile.instrument, path)


def load_profile(profile_id: str) -> Profile:
    """Load a built-in instrument's view by id, such as ``"bottles-v1"``."""
    return _view(instrument(profile_id))


def robot_profile(profile_id: str = "bottles-v1") -> RobotProfile:
    return RobotProfile(instrument(profile_id))


def keyboard_profile(profile_id: str = "piano-88") -> KeyboardProfile:
    return KeyboardProfile(instrument(profile_id))
