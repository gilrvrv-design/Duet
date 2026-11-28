"""Ensembles (spec Phase 4): many lines, many instruments, one performance.

``assign`` decides which line each instrument plays. The whole piece shares one
transposition so it stays in key; each part may also move by octaves. Robots play one
note at a time, so they get the top line of a track (its "skyline"). ``perform_ensemble``
then plays every robot and the pianist's lights from one clock.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from duet.conductor import Clock, Device, Performance, build_messages, home_all, stream
from duet.midi_io import TrackNote
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import message_time_us
from duet.repair import repair_robot
from duet.score import DUO, DuetScore
from duet.timing import bar_and_beat, seconds_per_beat


@dataclass(frozen=True)
class Instrument:
    name: str
    robot: RobotProfile | None = None  # None: a person
    low: int = 48  # a person's comfortable range
    high: int = 84

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


def _fit(notes: list[TrackNote], instrument: Instrument, shift: int) -> tuple[float, int]:
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


def assign(tracks: dict[str, list[TrackNote]], instruments: list[Instrument]) -> Assignment:
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


@dataclass
class Player:
    instrument: Instrument
    score: DuetScore  # robot events for a robot; pianist events for the person
    devices: list[Device]


def build_players(
    tracks: dict[str, list[TrackNote]],
    instruments: list[Instrument],
    assignment: Assignment,
    tempo_bpm: float,
    time_signature: tuple[int, int],
    devices: dict[str, list[Device]],
) -> list[Player]:
    """One score per instrument, each made playable (robots keep the tempo)."""
    per_bar = time_signature[0]
    players = []
    for instrument in instruments:
        if instrument.name not in assignment.parts:
            continue
        track, octave = assignment.parts[instrument.name]
        notes = skyline(tracks[track]) if instrument.is_robot else tracks[track]
        part = DUO.bot if instrument.is_robot else DUO.human
        events = []
        for n in notes:
            bar, beat = bar_and_beat(n.beat, per_bar)
            if beat >= per_bar + 1:
                continue
            events.append(
                {
                    "part": part,
                    "bar": bar,
                    "beat": beat,
                    "dur": n.dur,
                    "pitch": n.pitch + assignment.transpose + octave,
                    "vel": n.vel,
                }
            )
        score = DuetScore.model_validate(
            {
                "meta": {
                    "title": f"{track} ({instrument.name})",
                    "tempo_bpm": tempo_bpm,
                    "time_signature": list(time_signature),
                },
                "events": events,
            }
        )
        if instrument.is_robot:
            fitted = score.with_events([e for e in score.events if instrument.fits(e.pitch)])
            score = repair_robot(fitted, instrument.robot, part=DUO.bot, keep_tempo=True).score
        players.append(Player(instrument, score, devices.get(instrument.name, [])))
    return players


def perform_ensemble(
    players: list[Player],
    keyboard: KeyboardProfile,
    clock: Clock,
    lookahead_s: float = 0.5,
    buffer_s: float = 0.3,
) -> dict[str, Performance]:
    """Home every rig, start everyone at the same moment, and stream one time-ordered
    message list, each message to its own player's devices."""
    from duet.plans import robot_plan
    from duet.protocol import LedFrameAt

    home_all([d for p in players for d in p.devices])
    silent = _silent_robot(players)
    plans = {
        p.instrument.name: robot_plan(p.score, p.instrument.robot or silent, part=DUO.bot)
        for p in players
    }
    first = players[0].score
    count_in_s = first.meta.beats_per_bar * seconds_per_beat(first.meta.tempo_bpm)
    preroll = max(
        (plans[p.instrument.name].preroll_s for p in players if p.instrument.is_robot),
        default=0.0,
    )
    start = clock.now_us() + round((buffer_s + max(count_in_s, preroll)) * 1_000_000)
    timeline, results, owner = [], {}, {}
    # The lights show the person's part and count everyone in, once.
    lights = next((p for p in players if not p.instrument.is_robot), None)
    for p in players:
        messages, planned = build_messages(
            p.score,
            p.instrument.robot or silent,
            keyboard,
            start,
            count_in=p is (lights or players[0]),
            plan=plans[p.instrument.name],
        )
        if p.instrument.is_robot and lights is not None:
            messages = [m for m in messages if not isinstance(m, LedFrameAt)]
        results[p.instrument.name] = Performance(start_us=start, planned=planned)
        for i, m in enumerate(messages):
            timeline.append((message_time_us(m), i, m))
            owner[id(m)] = p
    timeline.sort(key=lambda s: (s[0], s[1]))

    def send(msg) -> None:
        player = owner[id(msg)]
        for device in player.devices:
            device.send(msg)
        results[player.instrument.name].messages_sent += 1

    stream([m for _, _, m in timeline], clock, round(lookahead_s * 1_000_000), send)
    return results


def _silent_robot(players: list[Player]) -> RobotProfile:
    """A person's part has no robot notes, but planning needs a profile: any robot's."""
    robot = next((p.instrument.robot for p in players if p.instrument.is_robot), None)
    if robot is None:
        raise ValueError("an ensemble needs at least one robot")
    return robot
