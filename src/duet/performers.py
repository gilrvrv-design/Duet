"""Who plays each part (docs/design/esp-first.md): a bot or a human, on an instrument.

Each performer owns the rule for what it can play. A bot's rule comes from its
mechanism (a carriage-striker cannot be in two places at once); a human's from the
skill levels (duet.difficulty). Code asks the part's performer and never asks whether a
part is "the robot".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType

from duet import midi_bot
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.instruments import CarriageStriker, Instrument, MidiOut, instrument
from duet.profile import KeyboardProfile, RobotProfile
from duet.repair import RepairResult, repair_robot
from duet.score import MIN_LEVEL, DuetScore, LineUpError

NO_OVERRIDES: Mapping[str, Instrument] = MappingProxyType({})


@dataclass(frozen=True)
class Bot:
    """A bot playing ``part``; what it can play depends on its mechanism: a carriage with
    a striker (travel time, one note at a time, duty cycle) or MIDI out (range and
    polyphony)."""

    part: str
    instrument: Instrument

    @property
    def mechanism(self) -> CarriageStriker | MidiOut:
        return self.instrument.bot

    @property
    def moves(self) -> bool:
        """Has a carriage: one per device, and it must be homed before playing."""
        return isinstance(self.mechanism, CarriageStriker)

    @cached_property
    def profile(self) -> RobotProfile:  # how the planner sees a carriage-striker bot
        return RobotProfile(self.instrument)

    def problems(self, score: DuetScore) -> list[str]:
        if self.moves:
            return check_robot(score, self.profile, part=self.part).feedback().splitlines()
        return midi_bot.problems(score, self.part, self.instrument)

    def repair(self, score: DuetScore, keep_tempo: bool = False) -> RepairResult:
        if self.moves:
            return repair_robot(score, self.profile, part=self.part, keep_tempo=keep_tempo)
        return midi_bot.repair(score, self.part, self.instrument)


@dataclass(frozen=True)
class Human:
    part: str
    instrument: Instrument
    level: int | None  # the target skill level; None: any

    @cached_property
    def profile(self) -> KeyboardProfile:  # how the light guide sees a keyboard
        return KeyboardProfile(self.instrument)

    def problems(self, score: DuetScore) -> list[str]:
        return check_pianist(score, self.profile, part=self.part, target_level=self.level)

    def difficulty(self, score: DuetScore) -> int:
        return pianist_difficulty(score, part=self.part)


Performer = Bot | Human


Instruments = Mapping[str, Instrument]  # by id: the ones in use, e.g. a calibrated rig


def in_use(*profiles: RobotProfile | KeyboardProfile) -> dict[str, Instrument]:
    """The instruments a command plays, by id (say, a calibrated rig from a file)."""
    return {p.id: p.instrument for p in profiles}


def performer(score: DuetScore, part: str, instruments: Instruments = NO_OVERRIDES) -> Performer:
    """The part's performer, on the instrument in use: ``instruments`` (say, a rig's
    a calibrated instrument) before the built-in one with the same id."""
    info = score.parts[part]
    try:
        inst = instruments.get(info.instrument) or instrument(info.instrument)
    except KeyError:
        raise LineUpError(f"part {part!r}: unknown instrument {info.instrument!r}") from None
    if info.performer not in inst.performers:
        raise LineUpError(
            f"part {part!r}: {inst.name} cannot be played by a {info.performer} "
            f"(it can by: {', '.join(inst.performers)})"
        )
    if info.performer == "bot":
        return Bot(part, inst)
    return Human(part, inst, score.meta.difficulty_target)


def performers(score: DuetScore, instruments: Instruments = NO_OVERRIDES) -> list[Performer]:
    return [performer(score, name, instruments) for name in score.parts]


def score_problems(
    score: DuetScore, instruments: Instruments = NO_OVERRIDES
) -> dict[str, list[str]]:
    """What each part's performer cannot play; empty lists when the score is playable."""
    return {p.part: p.problems(score) for p in performers(score, instruments)}


def human_difficulty(score: DuetScore) -> int:
    """How hard the score is for the people playing it: its hardest human part."""
    humans = [p for p in performers(score) if isinstance(p, Human)]
    return max((h.difficulty(score) for h in humans), default=MIN_LEVEL)


def repair_bots(
    score: DuetScore, instruments: Instruments = NO_OVERRIDES, keep_tempo: bool = False
) -> RepairResult:
    """Make every bot part playable; humans' parts are left as written."""
    changes = []
    for bot in (p for p in performers(score, instruments) if isinstance(p, Bot)):
        result = bot.repair(score, keep_tempo)
        score, changes = result.score, changes + result.changes
    return RepairResult(score, changes)
