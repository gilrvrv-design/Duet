"""Instruments (docs/design/esp-first.md): what sounds, and how it can be played.

An instrument file says what the instrument is (its notes, as measured, and its sound)
and how it can be played: by a bot (``bot:``, a mechanism with its physical limits) and
by a human (``human:``, how the notes are shown to them). An instrument offers only the
performers it has a section for. Instrument facts live in YAML, not in code; a new
instrument is a new file, and a new way of playing is a new mechanism or guide here.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, model_validator

from duet.pitch import cents_between, midi_to_hz, midi_to_name
from duet.score import FrozenModel, Pitch

SCHEMA = "duet-instrument/1"


class Note(FrozenModel):
    """One sounding note: its name, and its measured pitch where that can drift (a
    bottle's water level); an equal-tempered key needs no ``hz``."""

    name: Pitch
    hz: float | None = Field(None, gt=0)

    @property
    def midi(self) -> int:
        return self.name

    @property
    def sounding_hz(self) -> float:
        return self.hz if self.hz is not None else midi_to_hz(self.name)


class Sound(FrozenModel):
    decay_ms: float = Field(gt=0)
    # Overtones as multiples of the fundamental. Struck glass is not harmonic; the
    # listener masks these while a bottle rings (FR-H2).
    partials: tuple[float, ...] = (1.0, 2.0, 3.0)


class CalibrationInfo(FrozenModel):
    version: int = Field(ge=1)
    date: str  # ISO 8601
    source: str = ""


# How a bot plays ------------------------------------------------------------------


class Kinematics(FrozenModel):
    steps_per_mm: float = Field(gt=0)
    v_max_mm_s: float = Field(gt=0)
    a_max_mm_s2: float = Field(gt=0)
    settle_ms: float = Field(0, ge=0)
    travel_steps: int = Field(gt=0)


class Striker(FrozenModel):
    pulse_us: tuple[int, int]
    recovery_ms: float = Field(ge=0)
    latency_ms: float = Field(0, ge=0)
    duty_limit: float = Field(0.2, gt=0, le=1)
    duty_window_s: float = Field(10.0, gt=0)  # the limit is on-time over any window this long

    @model_validator(mode="after")
    def _check_pulse(self) -> Striker:
        if not 0 < self.pulse_us[0] <= self.pulse_us[1]:
            raise ValueError("pulse_us must be (min, max) with 0 < min <= max")
        return self

    def pulse_for_velocity(self, vel: int) -> int:
        low, high = self.pulse_us
        return round(low + (high - low) * (vel - 1) / 126)


class CarriageStriker(FrozenModel):
    """One striker on a carriage that slides along the notes: one note at a time, and
    moving between notes takes time (duet.kinematics)."""

    mechanism: Literal["carriage_striker"]
    positions: tuple[int, ...] = Field(min_length=1)  # carriage steps, one per note
    kinematics: Kinematics
    striker: Striker

    @model_validator(mode="after")
    def _check_positions(self) -> CarriageStriker:
        steps = list(self.positions)
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("note positions must be strictly increasing")
        if steps[-1] > self.kinematics.travel_steps:
            raise ValueError("a note lies beyond the carriage travel")
        return self


Mechanism = Annotated[CarriageStriker, Field(discriminator="mechanism")]


# How a human is guided --------------------------------------------------------------


class LedStrip(FrozenModel):
    """A strip of LEDs above a piano-style keyboard: each key lights the LEDs over it."""

    guide: Literal["led_strip"]
    leds_per_m: float = Field(gt=0)
    white_key_mm: float = Field(gt=0)
    first_led_mm: float = 0.0  # from the strip's first LED to the lowest key's left edge


Guide = Annotated[LedStrip, Field(discriminator="guide")]


class HumanPlay(FrozenModel):
    guide: Guide


# The instrument ---------------------------------------------------------------------


class Instrument(FrozenModel):
    schema_id: Literal["duet-instrument/1"] = Field(SCHEMA, alias="schema")
    id: str
    name: str
    # Either the notes one by one (tuned bottles, bars), or every semitone in a range.
    notes: tuple[Note, ...] = ()
    range: tuple[Pitch, Pitch] | None = None
    sound: Sound | None = None
    # How far a note may sound from its name and still play that note. Calibration
    # renames a note that drifts further (calibration.RENAME_CENTS).
    tolerance_cents: float = Field(50.0, gt=0, le=100)
    calibration: CalibrationInfo | None = None
    bot: Mechanism | None = None
    human: HumanPlay | None = None

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self) -> Instrument:
        if bool(self.notes) == (self.range is not None):
            raise ValueError("give either notes or a range")
        if self.range is not None and self.range[0] > self.range[1]:
            raise ValueError("range: the low note is above the high note")
        if self.bot is None and self.human is None:
            raise ValueError("nothing can play it: give a bot or a human section")
        if len({n.midi for n in self.notes}) != len(self.notes):
            raise ValueError("two notes share a pitch")
        for n in self.notes:
            off = cents_between(midi_to_hz(n.midi), n.sounding_hz)
            if abs(off) > self.tolerance_cents:
                raise ValueError(
                    f"note {midi_to_name(n.midi)} sounds {n.sounding_hz:g} Hz, {off:+.0f} "
                    f"cents off its name (tolerance {self.tolerance_cents:g}); rename or "
                    "retune it"
                )
        if self.bot is not None and len(self.bot.positions) != len(self.notes):
            raise ValueError("the bot needs one position per note")
        return self

    @property
    def pitches(self) -> list[int]:
        if self.range is not None:
            return list(range(self.range[0], self.range[1] + 1))
        return [n.midi for n in self.notes]

    @property
    def performers(self) -> tuple[str, ...]:
        """Who can play it: "bot", "human", or both."""
        return tuple(p for p in ("bot", "human") if getattr(self, p) is not None)


def parse_instrument(data: dict) -> Instrument:
    return Instrument.model_validate(data)


def load_instrument_file(path: str | Path) -> Instrument:
    return parse_instrument(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def save_instrument_file(instrument: Instrument, path: str | Path) -> None:
    data = instrument.model_dump(mode="json", by_alias=True, exclude_none=True)
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@cache
def instrument(instrument_id: str) -> Instrument:
    """A built-in instrument by id, such as ``"bottles-v1"``."""
    resource = resources.files("duet.profiles") / f"{instrument_id}.yaml"
    if not resource.is_file():
        raise KeyError(f"unknown instrument: {instrument_id}")
    return parse_instrument(yaml.safe_load(resource.read_text(encoding="utf-8")))
