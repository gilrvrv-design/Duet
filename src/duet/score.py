"""The DuetScore: the one score format every input becomes (spec §4.1).

The score knows nothing about MIDI, LLMs or hardware. Pitches are stored as MIDI
numbers and written out as names, so JSON stays readable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
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

SCHEMA_ID = "duetscore/2"  # 2: named parts, each with an instrument and a performer

PartName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
PerformerKind = Literal["bot", "human"]  # who plays a part (duet.performers: how)
# Version 1 had exactly these two parts, played by these performers.
V1_PERFORMERS: dict[str, PerformerKind] = {"robot": "bot", "pianist": "human"}
COMMON_TIME = (4, 4)
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
    time_signature: tuple[int, int] = COMMON_TIME
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
    instrument: str  # an instrument id (duet.instruments)
    performer: PerformerKind
    role: str = "melody"
    hand: Literal["left", "right", "both"] | None = None
    range: tuple[Pitch, Pitch] | None = None

    @field_validator("range")
    @classmethod
    def _check_range(cls, value: tuple[int, int] | None) -> tuple[int, int] | None:
        if value is not None and value[0] > value[1]:
            raise ValueError("range low note is above the high note")
        return value


@dataclass(frozen=True)
class Duo:
    """A two-part line-up: one part for a bot, one for a human. Whatever makes a duet
    (the composer, MIDI import, the arranger, call and response) makes it for a Duo, so
    the parts' names and instruments are data, not code. ``DUO`` is the rig's own."""

    bot: str = "robot"
    bot_instrument: str = "bottles-v1"
    human: str = "pianist"
    human_instrument: str = "piano-88"

    def parts(
        self, human_range: tuple[int | str, int | str] | None = None, hand: str = "right"
    ) -> dict[str, PartInfo]:
        return {
            self.bot: PartInfo(instrument=self.bot_instrument, performer="bot", role="melody"),
            self.human: PartInfo(
                instrument=self.human_instrument,
                performer="human",
                role="accompaniment",
                hand=hand,
                range=human_range,
            ),
        }


DUO = Duo()


def _default_parts() -> dict[str, PartInfo]:
    return DUO.parts()


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
    # Repeats are not played: a score writes its bars out. Refused rather than ignored.
    repeat: int = Field(1, ge=1, le=1)


class Turn(_Model):
    bars: tuple[int, int]
    lead: PartName


class Annotation(_Model):
    bar: int = Field(ge=1)
    text: str


class LineUpError(ValueError):
    """The score's parts do not fit what was asked of it."""


def _from_v1(data: object) -> object:
    """Version 1 had exactly two parts, "robot" and "pianist", each naming an
    ``instrument_profile``: the bot played the first, a human the second."""
    if not isinstance(data, dict):
        return data
    schema = data.get("schema", data.get("schema_id"))
    parts = data.get("parts", {})
    is_v1 = schema == "duetscore/1" or any(
        isinstance(p, dict) and "instrument_profile" in p for p in parts.values()
    )
    if not is_v1:
        return data
    converted = {k: v for k, v in data.items() if k not in ("schema", "schema_id")}
    converted["schema"] = SCHEMA_ID
    converted["parts"] = {
        name: {
            **{k: v for k, v in info.items() if k != "instrument_profile"},
            "instrument": info["instrument_profile"],
            "performer": V1_PERFORMERS[name],
        }
        for name, info in parts.items()
    }
    return converted


class DuetScore(_Model):
    schema_id: Literal["duetscore/2"] = Field(SCHEMA_ID, alias="schema")
    meta: Meta = Field(default_factory=Meta)
    parts: dict[PartName, PartInfo] = Field(default_factory=_default_parts)
    events: tuple[Event, ...] = ()
    sections: tuple[Section, ...] = ()
    turns: tuple[Turn, ...] = ()
    annotations: tuple[Annotation, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _upgrade(cls, data: object) -> object:
        return _from_v1(data)

    @model_validator(mode="after")
    def _check_consistency(self) -> DuetScore:
        if not self.parts:
            raise ValueError("a score needs at least one part")
        for i, event in enumerate(self.events):
            if event.part not in self.parts:
                raise ValueError(f"events[{i}]: no part named {event.part!r}")
        for i, turn in enumerate(self.turns):
            if turn.lead not in self.parts:
                raise ValueError(f"turns[{i}]: no part named {turn.lead!r}")
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

    def part_played_by(self, performer: PerformerKind) -> str:
        """The one part a bot (or a human) plays, for features made for duets (swapping
        the parts, teaching a part). A score with none or several says so."""
        names = self.parts_played_by(performer)
        if len(names) != 1:
            raise LineUpError(
                f"this needs exactly one {performer} part; the score has {names or 'none'}"
            )
        return names[0]

    def parts_played_by(self, performer: PerformerKind) -> list[str]:
        """The names of the parts a bot (or a human) plays, in score order."""
        return [name for name, info in self.parts.items() if info.performer == performer]

    def part_events(self, part: PartName) -> list[Event]:
        """Events of one part, sorted by position."""
        return sorted((e for e in self.events if e.part == part), key=lambda e: (e.bar, e.beat))

    def with_events(self, events: list[Event] | tuple[Event, ...]) -> DuetScore:
        return self.revised({"events": tuple(events)})

    def only(self, part: PartName) -> DuetScore:
        """One part alone: the robot solo, or the pianist practising alone. Turns (who
        plays when) mean nothing for one part and are dropped, as are sections that end
        after the remaining notes do."""
        if part not in self.parts:
            raise LineUpError(f"no part named {part!r}; the score has {list(self.parts)}")
        events = tuple(e for e in self.events if e.part == part)
        solo = self.revised({"events": events, "turns": (), "sections": ()})
        last = solo.bar_count
        sections = tuple(s for s in self.sections if last and s.bars[1] <= last)
        return solo.revised({"sections": sections}) if sections else solo

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
