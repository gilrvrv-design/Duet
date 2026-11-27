"""Audio file -> Transcription -> MIDI (spec §5.14.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido

from duet.audio.analysis import estimate_key, estimate_tempo, quantize
from duet.audio.io import DEFAULT_SR, load_audio
from duet.audio.melody import PyinTranscriber
from duet.audio.notes import NoteEvent, Transcriber

TICKS = 480


@dataclass
class Transcription:
    notes: list[NoteEvent]
    tempo_bpm: float
    key: str
    duration_s: float
    model: str
    route: str = "melody"
    warnings: list[str] = field(default_factory=list)

    def tracks(self) -> list[str]:
        return sorted({n.track for n in self.notes})


def transcribe(
    audio, sr: int, transcriber: Transcriber | None = None, route: str = "melody"
) -> Transcription:
    transcriber = transcriber or PyinTranscriber()
    notes = transcriber.transcribe(audio, sr)
    warnings = []
    if not notes:
        warnings.append("no notes found; is the recording silent or very noisy?")
    low = [n for n in notes if n.confidence < 0.6]
    if low:
        warnings.append(f"{len(low)} note(s) have low confidence")
    return Transcription(
        notes=notes,
        tempo_bpm=estimate_tempo(notes, audio, sr),
        key=estimate_key(notes)[0],
        duration_s=round(audio.size / sr, 3),
        model=transcriber.name,
        route=route,
        warnings=warnings,
    )


def transcribe_file(path: str | Path, transcriber: Transcriber | None = None) -> Transcription:
    audio, sr = load_audio(path, DEFAULT_SR)
    return transcribe(audio, sr, transcriber)


def transcription_to_midi(
    t: Transcription, grid_beats: float = 0.25, strength: float = 1.0
) -> mido.MidiFile:
    """Type 1 MIDI, one track per transcribed instrument, on the estimated beat grid."""
    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS)
    meta = mido.MidiTrack(
        [
            mido.MetaMessage("track_name", name="transcription", time=0),
            mido.MetaMessage("set_tempo", tempo=round(60_000_000 / t.tempo_bpm), time=0),
            mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
            mido.MetaMessage("marker", text=f"key:{t.key}", time=0),
            mido.MetaMessage("end_of_track", time=0),
        ]
    )
    midi.tracks.append(meta)
    for channel, name in enumerate(t.tracks()):
        placed = quantize(
            [n for n in t.notes if n.track == name], t.tempo_bpm, grid_beats, strength
        )
        events = []
        for start, dur, n in placed:
            on, off = round(start * TICKS), round((start + dur) * TICKS)
            events.append(
                (on, 1, mido.Message("note_on", channel=channel, note=n.pitch, velocity=n.velocity))
            )
            events.append(
                (
                    max(off, on + 1),
                    0,
                    mido.Message("note_off", channel=channel, note=n.pitch, velocity=0),
                )
            )
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        now = 0
        for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(msg.copy(time=tick - now))
            now = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)
    return midi
