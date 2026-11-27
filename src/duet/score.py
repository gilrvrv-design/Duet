"""The DuetScore: the one score format every input becomes (spec §4.1).

The score knows nothing about MIDI, LLMs or hardware. Pitches are stored as MIDI
numbers and written out as names, so JSON stays readable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from duet.pitch import PitchError, midi_to_name, to_midi

SCHEMA_ID = "duetscore/1"

PartName = Literal["robot", "pianist"]
PARTS: tuple[PartName, ...] = ("robot", "pianist")
MIN_LEVEL, MAX_LEVEL = 1, 5  # pianist difficulty levels; the rules are in duet.difficulty
Level = Annotated[int, Field(ge=MIN_LEVEL, le=MAX_LEVEL)]
MIN_TEMPO_BPM, MAX_TEMPO_BPM = 20.0, 300.0  # exclusive, inclusive
Tempo = Annotated[float, Field(gt=MIN_TEMPO_BPM, le=MAX_TEMPO_BPM)]


def clamp_tempo(tempo_bpm: float) -> float:
    """The nearest tempo a score allows (to a tenth of a bpm)."""
    return min(MAX_TEMPO_BPM, max(MIN_TEMPO_BPM + 0.1, tempo_bpm))


def _parse_pitch(value: object) -> int:
    if isinstance(value, (str, int)):
        try:
            return to_midi(value)
        except PitchError as exc:
            raise ValueError(str(exc)) from exc
    raise ValueError(f"pitch must be a name or MIDI number, got {value!r}")


Pitch = Annotated[
    int, BeforeValidator(_parse_pitch), PlainSerializer(midi_to_name, return_type=str)
]


class FrozenModel(BaseModel):
    """Immutable, strict model. Change one with ``revised``, never ``model_copy``:
    ``model_copy`` skips validation, so it can build a score or profile that breaks a
    rule every other part of the system relies on."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def revised(self, update: dict) -> Self:
        """A validated copy with some fields changed."""
        return type(self).model_validate({**dict(self), **update})


_Model = FrozenModel


class Meta(_Model):
    title: str = "Untitled duet"
    prompt: str | None = None
    key: str = "C major"
    time_signature: tuple[int, int] = (4, 4)
    tempo_bpm: Tempo = 100.0
    style_tags: tuple[str, ...] = ()
    difficulty_target: Level | None = None

    @field_validator("time_signature")
    @classmethod
    def _check_time_signature(cls, value: tuple[int, int]) -> tuple[int, int]:
        beats, unit = value
        if not 1 <= beats <= 16 or unit not in (2, 4, 8, 16):
            raise ValueError(f"unsupported time signature {beats}/{unit}")
        return value

    @property
    def beats_per_bar(self) -> int:
        return self.time_signature[0]


class PartInfo(_Model):
    instrument_profile: str
    role: str = "melody"
    hand: Literal["left", "right", "both"] | None = None
    range: tuple[Pitch, Pitch] | None = None

    @field_validator("range")
    @classmethod
    def _check_range(cls, value: tuple[int, int] | None) -> tuple[int, int] | None:
        if value is not None and value[0] > value[1]:
            raise ValueError("range low note is above the high note")
        return value


def _default_parts() -> dict[str, PartInfo]:
    return {
        "robot": PartInfo(instrument_profile="bottles-v1", role="melody"),
        "pianist": PartInfo(instrument_profile="piano-88", role="accompaniment", hand="right"),
    }


class Event(_Model):
    """One note. ``bar`` and ``beat`` are 1-based; ``dur`` is in beats."""

    part: PartName
    bar: int = Field(ge=1)
    beat: float = Field(ge=1.0)
    dur: float = Field(gt=0)
    pitch: Pitch
    vel: int = Field(80, ge=1, le=127)
    finger: int | None = Field(None, ge=1, le=5)
    hint: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class Section(_Model):
    name: str
    bars: tuple[int, int]
    repeat: int = Field(1, ge=1)


class Turn(_Model):
    bars: tuple[int, int]
    lead: PartName


class Annotation(_Model):
    bar: int = Field(ge=1)
    text: str


class DuetScore(_Model):
    schema_id: Literal["duetscore/1"] = Field(SCHEMA_ID, alias="schema")
    meta: Meta = Field(default_factory=Meta)
    parts: dict[PartName, PartInfo] = Field(default_factory=_default_parts)
    events: tuple[Event, ...] = ()
    sections: tuple[Section, ...] = ()
    turns: tuple[Turn, ...] = ()
    annotations: tuple[Annotation, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def _check_consistency(self) -> DuetScore:
        missing = set(PARTS) - set(self.parts)
        if missing:
            raise ValueError(f"missing parts: {sorted(missing)}")
        beats = self.meta.beats_per_bar
        for i, event in enumerate(self.events):
            if event.beat >= beats + 1:
                raise ValueError(
                    f"events[{i}]: beat {event.beat} is outside a bar of {beats} beats"
                )
        last = self.bar_count
        for kind, spans in (("sections", self.sections), ("turns", self.turns)):
            for i, item in enumerate(spans):
                start, end = item.bars
                if not 1 <= start <= end or (last and end > last):
                    raise ValueError(f"{kind}[{i}]: bars {item.bars} outside 1..{last}")
        return self

    @property
    def bar_count(self) -> int:
        """Number of bars the notes occupy (a note may ring into the next bar)."""
        if not self.events:
            return 0
        beats = self.meta.beats_per_bar
        end = max((e.bar - 1) * beats + (e.beat - 1) + e.dur for e in self.events)
        return max(1, -(-int(end * 1000) // (beats * 1000)))

    def part_events(self, part: PartName) -> list[Event]:
        """Events of one part, sorted by position."""
        return sorted((e for e in self.events if e.part == part), key=lambda e: (e.bar, e.beat))

    def with_events(self, events: list[Event] | tuple[Event, ...]) -> DuetScore:
        return self.revised({"events": tuple(events)})

    def with_tempo(self, tempo_bpm: float) -> DuetScore:
        return self.revised({"meta": self.meta.revised({"tempo_bpm": tempo_bpm})})

    def to_dict(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def load_score(source: str | Path | dict) -> DuetScore:
    """Load a DuetScore from a dict, a JSON string or a path to a JSON file."""
    if isinstance(source, dict):
        return DuetScore.model_validate(source)
    if isinstance(source, Path) or (
        isinstance(source, str) and not source.lstrip().startswith("{")
    ):
        source = Path(source).read_text(encoding="utf-8")
    return DuetScore.model_validate_json(source)
