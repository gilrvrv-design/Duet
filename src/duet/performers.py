"""Who plays each part (docs/design/esp-first.md): a bot or a human, on an instrument.

Each performer owns the rule for what it can play. A bot's rule comes from its
mechanism (a carriage-striker cannot be in two places at once); a human's from the
skill levels (duet.difficulty). Code asks the part's performer and never asks whether a
part is "the robot".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import DEFAULT_MARGIN_S, Report, check_robot
from duet.instruments import Instrument, instrument
from duet.profile import KeyboardProfile, RobotProfile
from duet.repair import RepairResult, repair_robot
from duet.score import MIN_LEVEL, DuetScore, LineUpError

NO_OVERRIDES: Mapping[str, Instrument] = MappingProxyType({})


@dataclass(frozen=True)
class Bot:
    part: str
    instrument: Instrument

    @property
    def profile(self) -> RobotProfile:  # the carriage-striker view, until step 1e
        return RobotProfile.from_instrument(self.instrument)

    def report(self, score: DuetScore, margin_s: float = DEFAULT_MARGIN_S) -> Report:
        """What the mechanism cannot play, by note, for repair."""
        return check_robot(score, self.profile, part=self.part, margin_s=margin_s)

    def problems(self, score: DuetScore) -> list[str]:
        return self.report(score).feedback().splitlines()

    def repair(self, score: DuetScore, keep_tempo: bool = False) -> RepairResult:
        return repair_robot(score, self.profile, part=self.part, keep_tempo=keep_tempo)


@dataclass(frozen=True)
class Human:
    part: str
    instrument: Instrument
    level: int | None  # the target skill level; None: any

    @property
    def profile(self) -> KeyboardProfile:  # the keyboard view, until step 1e
        return KeyboardProfile.from_instrument(self.instrument)

    def problems(self, score: DuetScore) -> list[str]:
        return check_pianist(score, self.profile, part=self.part, target_level=self.level)

    def difficulty(self, score: DuetScore) -> int:
        return pianist_difficulty(score, part=self.part)


Performer = Bot | Human


Instruments = Mapping[str, Instrument]  # by id: the ones in use, e.g. a calibrated rig


def performer(score: DuetScore, part: str, instruments: Instruments = NO_OVERRIDES) -> Performer:
    """The part's performer, on the instrument in use: ``instruments`` (say, a rig's
    calibrated bottles) before the built-in one with the same id."""
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
