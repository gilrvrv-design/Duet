"""Instrument profiles (spec §7.2): everything the system knows about an instrument.

Instrument facts live in YAML, not in code. New instruments are new profiles.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from duet.pitch import cents_between, midi_to_hz
from duet.score import Pitch


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Bottle(_Model):
    name: Pitch
    hz: float = Field(gt=0)
    steps: int = Field(ge=0)

    @property
    def midi(self) -> int:
        return self.name


class Kinematics(_Model):
    steps_per_mm: float = Field(gt=0)
    v_max_mm_s: float = Field(gt=0)
    a_max_mm_s2: float = Field(gt=0)
    settle_ms: float = Field(0, ge=0)
    travel_steps: int = Field(gt=0)


class Striker(_Model):
    pulse_us: tuple[int, int]
    recovery_ms: float = Field(ge=0)
    latency_ms: float = Field(0, ge=0)
    duty_limit: float = Field(0.2, gt=0, le=1)

    @model_validator(mode="after")
    def _check_pulse(self) -> Striker:
        if not 0 < self.pulse_us[0] <= self.pulse_us[1]:
            raise ValueError("pulse_us must be (min, max) with 0 < min <= max")
        return self

    def pulse_for_velocity(self, vel: int) -> int:
        low, high = self.pulse_us
        return round(low + (high - low) * (vel - 1) / 126)


class Sound(_Model):
    decay_ms: float = Field(gt=0)


class RobotProfile(_Model):
    id: str
    kind: Literal["robot.mallet.monophonic"]
    notes: tuple[Bottle, ...] = Field(min_length=1)
    kinematics: Kinematics
    striker: Striker
    sound: Sound

    @model_validator(mode="after")
    def _check_notes(self) -> RobotProfile:
        steps = [b.steps for b in self.notes]
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("bottle positions must be strictly increasing")
        if steps[-1] > self.kinematics.travel_steps:
            raise ValueError("a bottle lies beyond the carriage travel")
        if len({b.midi for b in self.notes}) != len(self.notes):
            raise ValueError("two bottles share a pitch")
        return self

    @property
    def pitches(self) -> list[int]:
        return [b.midi for b in self.notes]

    def bottle_index(self, midi: int, tolerance_cents: float = 50.0) -> int | None:
        """Index of the bottle that sounds ``midi`` within the tolerance, using measured pitch."""
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
    kind: Literal["keyboard"]
    low: Pitch
    high: Pitch
    led: Led

    def contains(self, midi: int) -> bool:
        return self.low <= midi <= self.high


Profile = RobotProfile | KeyboardProfile


def _parse(data: dict) -> Profile:
    if data.get("kind") == "keyboard":
        return KeyboardProfile.model_validate(data)
    return RobotProfile.model_validate(data)


def load_profile_file(path: str | Path) -> Profile:
    return _parse(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


@cache
def load_profile(profile_id: str) -> Profile:
    """Load a built-in profile by id, such as ``"bottles-v1"``."""
    resource = resources.files("duet.profiles") / f"{profile_id}.yaml"
    if not resource.is_file():
        raise KeyError(f"unknown instrument profile: {profile_id}")
    return _parse(yaml.safe_load(resource.read_text(encoding="utf-8")))


def robot_profile(profile_id: str = "bottles-v1") -> RobotProfile:
    profile = load_profile(profile_id)
    if not isinstance(profile, RobotProfile):
        raise TypeError(f"{profile_id} is not a robot profile")
    return profile


def keyboard_profile(profile_id: str = "piano-88") -> KeyboardProfile:
    profile = load_profile(profile_id)
    if not isinstance(profile, KeyboardProfile):
        raise TypeError(f"{profile_id} is not a keyboard profile")
    return profile
