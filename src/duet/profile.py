"""Instrument profiles: the views of an instrument that the planner, conductor and
checks use today.

Being replaced: instruments are now ``duet.instruments.Instrument`` (one file per
instrument, with ``bot`` and ``human`` sections). ``RobotProfile`` is an instrument
played by a carriage-striker bot; ``KeyboardProfile`` is a keyboard played by a human
following an LED strip. Both are built from instruments and saved as instruments; code
moves to the new model slice by slice and these views go (docs/design/esp-first.md).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator

from duet.instruments import (
    CalibrationInfo,
    CarriageStriker,
    HumanPlay,
    Instrument,
    Kinematics,
    LedStrip,
    Note,
    Sound,
    Striker,
    instrument,
    load_instrument_file,
    save_instrument_file,
)
from duet.pitch import cents_between, midi_to_hz, midi_to_name
from duet.score import FrozenModel, Pitch

_Model = FrozenModel
__all__ = ["CalibrationInfo", "Kinematics", "Sound", "Striker"]


class Bottle(_Model):
    name: Pitch
    hz: float = Field(gt=0)
    steps: int = Field(ge=0)

    @property
    def midi(self) -> int:
        return self.name


class RobotProfile(_Model):
    id: str
    name: str
    notes: tuple[Bottle, ...] = Field(min_length=1)
    kinematics: Kinematics
    striker: Striker
    sound: Sound
    calibration: CalibrationInfo | None = None
    midi_program: int = 0
    # How far a bottle may sound from its name and still play that note. Calibration
    # renames a bottle that drifts further (calibration.RENAME_CENTS).
    tolerance_cents: float = Field(50.0, gt=0, le=100)

    @model_validator(mode="after")
    def _check_notes(self) -> RobotProfile:
        steps = [b.steps for b in self.notes]
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("bottle positions must be strictly increasing")
        if steps[-1] > self.kinematics.travel_steps:
            raise ValueError("a bottle lies beyond the carriage travel")
        if len({b.midi for b in self.notes}) != len(self.notes):
            raise ValueError("two bottles share a pitch")
        for b in self.notes:
            off = cents_between(midi_to_hz(b.midi), b.hz)
            if abs(off) > self.tolerance_cents:
                raise ValueError(
                    f"bottle {midi_to_name(b.midi)} sounds {b.hz:g} Hz, {off:+.0f} cents off "
                    f"its name (tolerance {self.tolerance_cents:g}); rename or retune it"
                )
        return self

    @classmethod
    def from_instrument(cls, inst: Instrument) -> RobotProfile:
        if not isinstance(inst.bot, CarriageStriker):
            raise TypeError(f"{inst.id} is not played by a carriage-striker bot")
        if inst.sound is None:
            raise ValueError(f"{inst.id}: a bot's instrument needs its sound (for listening)")
        return cls(
            id=inst.id,
            name=inst.name,
            notes=tuple(
                Bottle(name=n.midi, hz=n.sounding_hz, steps=steps)
                for n, steps in zip(inst.notes, inst.bot.positions, strict=True)
            ),
            kinematics=inst.bot.kinematics,
            striker=inst.bot.striker,
            sound=inst.sound,
            calibration=inst.calibration,
            midi_program=inst.midi_program,
            tolerance_cents=inst.tolerance_cents,
        )

    def to_instrument(self) -> Instrument:
        return Instrument(
            id=self.id,
            name=self.name,
            notes=tuple(Note(name=b.midi, hz=b.hz) for b in self.notes),
            sound=self.sound,
            midi_program=self.midi_program,
            tolerance_cents=self.tolerance_cents,
            calibration=self.calibration,
            bot=CarriageStriker(
                mechanism="carriage_striker",
                positions=tuple(b.steps for b in self.notes),
                kinematics=self.kinematics,
                striker=self.striker,
            ),
        )

    @property
    def pitches(self) -> list[int]:
        return [b.midi for b in self.notes]

    def bottle_index(self, midi: int, tolerance_cents: float | None = None) -> int | None:
        """Index of the bottle that sounds ``midi`` within the tolerance (the profile's
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


class Led(_Model):
    leds_per_m: float = Field(gt=0)
    white_key_mm: float = Field(gt=0)
    first_led_mm: float = 0.0


class KeyboardProfile(_Model):
    id: str
    name: str
    low: Pitch
    high: Pitch
    led: Led
    midi_program: int = 0

    @classmethod
    def from_instrument(cls, inst: Instrument) -> KeyboardProfile:
        if inst.range is None or inst.human is None or not isinstance(inst.human.guide, LedStrip):
            raise TypeError(f"{inst.id} is not a keyboard played by a human with an LED strip")
        g = inst.human.guide
        return cls(
            id=inst.id,
            name=inst.name,
            low=inst.range[0],
            high=inst.range[1],
            midi_program=inst.midi_program,
            led=Led(
                leds_per_m=g.leds_per_m, white_key_mm=g.white_key_mm, first_led_mm=g.first_led_mm
            ),
        )

    def to_instrument(self) -> Instrument:
        guide = LedStrip(guide="led_strip", **self.led.model_dump())
        return Instrument(
            id=self.id,
            name=self.name,
            range=(self.low, self.high),
            midi_program=self.midi_program,
            human=HumanPlay(guide=guide),
        )

    def contains(self, midi: int) -> bool:
        return self.low <= midi <= self.high


Profile = RobotProfile | KeyboardProfile


def _view(inst: Instrument) -> Profile:
    """The view today's code uses: a bot's instrument as a RobotProfile, else a keyboard."""
    if inst.bot is not None:
        return RobotProfile.from_instrument(inst)
    return KeyboardProfile.from_instrument(inst)


def load_profile_file(path: str | Path) -> Profile:
    return _view(load_instrument_file(path))


def save_profile_file(profile: Profile, path: str | Path) -> None:
    save_instrument_file(profile.to_instrument(), path)


def load_profile(profile_id: str) -> Profile:
    """Load a built-in profile by id, such as ``"bottles-v1"``."""
    return _view(instrument(profile_id))


def robot_profile(profile_id: str = "bottles-v1") -> RobotProfile:
    return RobotProfile.from_instrument(instrument(profile_id))


def keyboard_profile(profile_id: str = "piano-88") -> KeyboardProfile:
    return KeyboardProfile.from_instrument(instrument(profile_id))
