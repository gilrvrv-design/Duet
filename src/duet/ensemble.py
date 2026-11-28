"""Ensembles (spec Phase 4): many lines, many instruments, one performance.

``assign`` decides which line each member plays. The whole piece shares one
transposition so it stays in key; each part may also move by octaves. Robots play one
note at a time, so they get the top line of a track (its "skyline"). ``build_score``
makes one score with a part per member; the conductor plays it, each part on its own
rig (``duet.conductor.perform`` with routes).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from duet.difficulty import COMFORTABLE_RANGE
from duet.instruments import Instrument
from duet.midi_io import TrackNote
from duet.profile import RobotProfile
from duet.repair import repair_robot
from duet.score import DUO, DuetScore, PartInfo
from duet.timing import bar_and_beat


@dataclass(frozen=True)
class Member:
    name: str
    robot: RobotProfile | None = None  # None: a person
    low: int = COMFORTABLE_RANGE[0]
    high: int = COMFORTABLE_RANGE[1]

    @property
    def is_robot(self) -> bool:
        return self.robot is not None

    def fits(self, pitch: int) -> bool:
        if self.robot is not None:
            return pitch in self.robot.pitches
        return self.low <= pitch <= self.high


def skyline(notes: list[TrackNote]) -> list[TrackNote]:
    """The top note at each onset: the line one striker can play."""
    tops: dict[float, TrackNote] = {}
    for n in notes:
        if n.beat not in tops or n.pitch > tops[n.beat].pitch:
            tops[n.beat] = n
    return [tops[b] for b in sorted(tops)]


def _fit(notes: list[TrackNote], instrument: Member, shift: int) -> tuple[float, int]:
    """(share of notes the instrument can play, best octave) at a global ``shift``."""
    line = skyline(notes) if instrument.is_robot else notes
    if not line:
        return 0.0, 0
    best = max(
        range(-36, 37, 12),
        key=lambda k: (sum(instrument.fits(n.pitch + shift + k) for n in line), -abs(k)),
    )
    return sum(instrument.fits(n.pitch + shift + best) for n in line) / len(line), best


@dataclass
class Assignment:
    transpose: int
    parts: dict[str, tuple[str, int]]  # instrument -> (track, octave shift)
    fit: dict[str, float]  # instrument -> share of notes it can play
    unused: list[str] = field(default_factory=list)  # tracks nobody plays


def assign(tracks: dict[str, list[TrackNote]], instruments: list[Member]) -> Assignment:
    """Try every global transposition and every way to give tracks to instruments; keep
    the one where the instruments can play the most of their lines (FR: Phase 4)."""
    names = [t for t in tracks if tracks[t]]
    best: tuple | None = None
    for shift in range(-6, 7):
        fits = {(t, i.name): _fit(tracks[t], i, shift) for t in names for i in instruments}
        slots = names + [None] * max(0, len(instruments) - len(names))
        for chosen in itertools.permutations(slots, len(instruments)):
            pairs = [(t, i) for t, i in zip(chosen, instruments, strict=True) if t]
            total = sum(fits[(t, i.name)][0] for t, i in pairs)
            octaves = sum(abs(fits[(t, i.name)][1]) for t, i in pairs)
            # Most notes playable; then most lines; then as written (no octave moves,
            # no transposition).
            key = (round(total, 6), len(pairs), -octaves, -abs(shift))
            if best is None or key > best[0]:
                best = (key, shift, chosen, fits)
    _, shift, chosen, fits = best
    parts = {
        i.name: (t, fits[(t, i.name)][1]) for t, i in zip(chosen, instruments, strict=True) if t
    }
    return Assignment(
        transpose=shift,
        parts=parts,
        fit={i: round(fits[(t, i)][0], 3) for i, (t, _) in parts.items()},
        unused=[t for t in names if t not in chosen],
    )


def build_score(
    tracks: dict[str, list[TrackNote]],
    members: list[Member],
    assignment: Assignment,
    tempo_bpm: float,
    time_signature: tuple[int, int],
    keyboard: str = DUO.human_instrument,
) -> tuple[DuetScore, dict[str, Instrument]]:
    """One score, one part per member that plays: a bot part per robot (its track's top
    line, made playable at the written tempo), a human part per person (on
    ``keyboard``). Returns the score and the robots' instruments in use."""
    per_bar = time_signature[0]
    parts: dict[str, PartInfo] = {}
    events: list[dict] = []
    playing: dict[str, Instrument] = {}
    for member in members:
        if member.name not in assignment.parts:
            continue
        track, octave = assignment.parts[member.name]
        notes = skyline(tracks[track]) if member.is_robot else tracks[track]
        if member.is_robot:
            instrument = member.robot.instrument
            if playing.setdefault(instrument.id, instrument) != instrument:
                raise ValueError(f"two different robots both call themselves {instrument.id!r}")
            parts[member.name] = PartInfo(instrument=instrument.id, performer="bot")
        else:
            parts[member.name] = PartInfo(
                instrument=keyboard,
                performer="human",
                role="accompaniment",
                range=(member.low, member.high),
            )
        for n in notes:
            bar, beat = bar_and_beat(n.beat, per_bar)
            pitch = n.pitch + assignment.transpose + octave
            if beat >= per_bar + 1 or not member.fits(pitch):
                continue
            events.append(
                {
                    "part": member.name,
                    "bar": bar,
                    "beat": beat,
                    "dur": n.dur,
                    "pitch": pitch,
                    "vel": n.vel,
                }
            )
    score = DuetScore.model_validate(
        {
            "meta": {
                "title": "Ensemble",
                "tempo_bpm": tempo_bpm,
                "time_signature": list(time_signature),
            },
            "parts": parts,
            "events": events,
        }
    )
    for member in members:
        if member.is_robot and member.name in parts:
            score = repair_robot(score, member.robot, part=member.name, keep_tempo=True).score
    return score, playing
