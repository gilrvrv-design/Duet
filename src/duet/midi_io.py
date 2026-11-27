"""DuetScore <-> MIDI (spec §5.2 FR-S6, FR-S7).

Export writes a Type 1 file: track 0 holds tempo, time signature and markers,
track 1 the robot part (channel 1), track 2 the pianist part (channel 2).

Import accepts any MIDI file. Tracks named "robot" / "pianist" are used as is.
Otherwise the track with the highest average pitch becomes the robot's melody and
the rest goes to the pianist; a single track is split by taking the top note of
each onset for the robot (a "skyline" split).
"""

from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import mido

from duet.score import DuetScore, Event, PartName, clamp_tempo
from duet.timing import bar_and_beat, beat_index

TICKS_PER_QUARTER = 480
CHANNELS: dict[PartName, int] = {"robot": 0, "pianist": 1}
PROGRAMS: dict[PartName, int] = {"robot": 13, "pianist": 0}  # GM xylophone, grand piano


def _ticks_per_beat(score_unit: int) -> int:
    return TICKS_PER_QUARTER * 4 // score_unit


def _us_per_quarter(tempo_bpm: float, unit: int) -> int:
    return round(60_000_000 / tempo_bpm * unit / 4)


def _track_from_abs(messages: list[tuple[int, int, mido.Message | mido.MetaMessage]]):
    """Build a track from (abs_tick, order, message); note-offs sort before note-ons."""
    track = mido.MidiTrack()
    now = 0
    for tick, _, msg in sorted(messages, key=lambda m: (m[0], m[1])):
        track.append(msg.copy(time=tick - now))
        now = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def score_to_midi(score: DuetScore) -> mido.MidiFile:
    beats, unit = score.meta.time_signature
    tpb = _ticks_per_beat(unit)
    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_QUARTER)

    meta: list = [
        (0, 0, mido.MetaMessage("track_name", name=score.meta.title)),
        (0, 0, mido.MetaMessage("time_signature", numerator=beats, denominator=unit)),
        (0, 0, mido.MetaMessage("set_tempo", tempo=_us_per_quarter(score.meta.tempo_bpm, unit))),
    ]
    for section in score.sections:
        tick = round(beat_index(section.bars[0], 1, beats) * tpb)
        meta.append((tick, 1, mido.MetaMessage("marker", text=f"section:{section.name}")))
    for turn in score.turns:
        tick = round(beat_index(turn.bars[0], 1, beats) * tpb)
        meta.append((tick, 1, mido.MetaMessage("marker", text=f"lead:{turn.lead}")))
    midi.tracks.append(_track_from_abs(meta))

    for part in ("robot", "pianist"):
        ch = CHANNELS[part]
        msgs: list = [
            (0, 0, mido.MetaMessage("track_name", name=part)),
            (0, 0, mido.Message("program_change", channel=ch, program=PROGRAMS[part])),
        ]
        for e in score.part_events(part):
            start = round(beat_index(e.bar, e.beat, beats) * tpb)
            end = max(start + 1, round(start + e.dur * tpb))
            msgs.append(
                (start, 2, mido.Message("note_on", channel=ch, note=e.pitch, velocity=e.vel))
            )
            msgs.append((end, 1, mido.Message("note_off", channel=ch, note=e.pitch, velocity=0)))
        midi.tracks.append(_track_from_abs(msgs))
    return midi


def score_to_midi_bytes(score: DuetScore) -> bytes:
    buffer = io.BytesIO()
    score_to_midi(score).save(file=buffer)
    return buffer.getvalue()


def save_midi(score: DuetScore, path: str | Path) -> None:
    score_to_midi(score).save(str(path))


@dataclass(frozen=True)
class _Note:
    track: int
    start: int  # ticks
    end: int
    pitch: int
    vel: int


Source = str | Path | bytes | mido.MidiFile
DEFAULT_TEMPO_US = 500_000  # MIDI's default: 120 bpm in quarter notes


def _open(source: Source) -> mido.MidiFile:
    if isinstance(source, mido.MidiFile):
        return source
    if isinstance(source, bytes):
        return mido.MidiFile(file=io.BytesIO(source))
    return mido.MidiFile(str(source))


def _bpm(tempo_us: int, unit: int) -> float:
    """MIDI tempo (microseconds per quarter) in beats of the time signature per minute."""
    return round(60_000_000 / tempo_us * unit / 4, 3)


def _read_notes(midi: mido.MidiFile, warnings: list[str] | None = None):
    """All notes plus the first tempo and time signature in the file. What a DuetScore
    cannot hold (later tempo or metre changes, notes never released) is reported in
    ``warnings``."""
    warnings = [] if warnings is None else warnings
    notes: list[_Note] = []
    names: dict[int, str] = {}
    tempo, signature = DEFAULT_TEMPO_US, (4, 4)
    seen_tempo = seen_sig = False
    tempo_changes = signature_changes = unreleased = 0
    for t, track in enumerate(midi.tracks):
        now = 0
        open_notes: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
        for msg in track:
            now += msg.time
            if msg.type == "track_name":
                names[t] = msg.name.strip().lower()
            elif msg.type == "set_tempo":
                if not seen_tempo:
                    tempo, seen_tempo = msg.tempo, True
                elif msg.tempo != tempo:
                    tempo_changes += 1
            elif msg.type == "time_signature":
                if not seen_sig:
                    signature, seen_sig = (msg.numerator, msg.denominator), True
                elif (msg.numerator, msg.denominator) != signature:
                    signature_changes += 1
            elif msg.type == "note_on" and msg.velocity > 0:
                open_notes[(msg.channel, msg.note)].append((now, msg.velocity))
            elif msg.type in ("note_off", "note_on") and open_notes[(msg.channel, msg.note)]:
                start, vel = open_notes[(msg.channel, msg.note)].pop(0)
                notes.append(_Note(t, start, now, msg.note, vel))
        unreleased += sum(len(v) for v in open_notes.values())
    if tempo_changes:
        warnings.append(f"{tempo_changes} later tempo change(s) ignored: one tempo per score")
    if signature_changes:
        warnings.append(f"{signature_changes} later time signature change(s) ignored")
    if unreleased:
        warnings.append(f"{unreleased} note(s) never released were left out")
    return notes, names, tempo, signature


def _assign_parts(notes: list[_Note], names: dict[int, str]) -> dict[int, PartName]:
    tracks = sorted({n.track for n in notes})
    named = {t: names[t] for t in tracks if names.get(t) in ("robot", "pianist")}
    if named:
        return {t: named.get(t, "pianist") for t in tracks}
    if len(tracks) == 1:
        return {}
    mean = {
        t: sum(n.pitch for n in notes if n.track == t) / sum(n.track == t for n in notes)
        for t in tracks
    }
    melody = max(tracks, key=lambda t: mean[t])
    return {t: "robot" if t == melody else "pianist" for t in tracks}


def _skyline(notes: list[_Note]) -> dict[_Note, PartName]:
    by_onset: dict[int, list[_Note]] = defaultdict(list)
    for n in notes:
        by_onset[n.start].append(n)
    parts: dict[_Note, PartName] = {}
    for group in by_onset.values():
        top = max(group, key=lambda n: n.pitch)
        for n in group:
            parts[n] = "robot" if n is top else "pianist"
    return parts


def midi_to_score(
    source: Source, title: str | None = None, quantize_beats: float | None = None
) -> DuetScore:
    return read_midi(source, title, quantize_beats)[0]


def read_midi(
    source: Source, title: str | None = None, quantize_beats: float | None = None
) -> tuple[DuetScore, list[str]]:
    """The score, and what the import had to ignore or change to make it."""
    warnings: list[str] = []
    midi = _open(source)
    notes, names, tempo_us, (beats, unit) = _read_notes(midi, warnings)
    tpb = midi.ticks_per_beat * 4 / unit
    tempo_bpm = _bpm(tempo_us, unit)

    by_track = _assign_parts(notes, names)
    part_of = {n: by_track[n.track] for n in notes} if by_track else _skyline(notes)

    def to_beats(ticks: int) -> float:
        value = ticks / tpb
        if quantize_beats:
            value = round(value / quantize_beats) * quantize_beats
        return round(value, 6)

    events = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        start = to_beats(n.start)
        dur = max(to_beats(n.end) - start, quantize_beats or 1 / 64)
        bar, beat = bar_and_beat(start, beats)
        events.append(
            Event(part=part_of[n], bar=bar, beat=beat, dur=round(dur, 6), pitch=n.pitch, vel=n.vel)
        )

    allowed = clamp_tempo(tempo_bpm)
    if allowed != tempo_bpm:
        warnings.append(
            f"tempo {tempo_bpm:g} bpm is outside what a score allows; using {allowed:g}"
        )
    meta = {"tempo_bpm": allowed, "time_signature": (beats, unit)}
    if title:
        meta["title"] = title
    score = DuetScore.model_validate({"meta": meta, "events": [e.model_dump() for e in events]})
    return score, warnings


@dataclass(frozen=True)
class TrackNote:
    beat: float  # 0-based, in beats of the time signature
    dur: float
    pitch: int
    vel: int


def midi_tracks(source: Source):
    """Every track with notes, by name: (tempo_bpm, time signature, {name: notes}).

    For ensembles (spec Phase 4), where each line goes to its own instrument.
    """
    midi = _open(source)
    notes, names, tempo_us, (beats, unit) = _read_notes(midi)
    tpb = midi.ticks_per_beat * 4 / unit
    tracks: dict[str, list[TrackNote]] = {}
    for n in sorted(notes, key=lambda n: (n.start, -n.pitch)):
        name = names.get(n.track) or f"track {n.track}"
        tracks.setdefault(name, []).append(
            TrackNote(
                round(n.start / tpb, 6), round(max(n.end - n.start, 1) / tpb, 6), n.pitch, n.vel
            )
        )
    return _bpm(tempo_us, unit), (beats, unit), tracks
