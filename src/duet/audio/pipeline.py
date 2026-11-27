"""Audio file -> Transcription -> MIDI (spec §5.14.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import mido

from duet.audio.analysis import estimate_key, estimate_tempo, quantize
from duet.audio.io import DEFAULT_SR, load_audio
from duet.audio.melody import PyinTranscriber
from duet.audio.notes import NoteEvent, Transcriber
from duet.progress import Progress, no_progress

TICKS = 480

LOW_CONFIDENCE = 0.6  # notes below this are flagged to the user


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Transcription:
        return cls(**{**data, "notes": [NoteEvent(**n) for n in data["notes"]]})


def transcribe(
    audio, sr: int, transcriber: Transcriber | None = None, route: str = "melody"
) -> Transcription:
    transcriber = transcriber or PyinTranscriber()
    notes = transcriber.transcribe(audio, sr)
    warnings = []
    if not notes:
        warnings.append("no notes found; is the recording silent or very noisy?")
    low = [n for n in notes if n.confidence < LOW_CONFIDENCE]
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


def transcribe_file(
    path: str | Path,
    transcriber: Transcriber | None = None,
    route: str = "auto",
    full_mix=None,
    progress: Progress = no_progress,
) -> Transcription:
    """Transcribe a file. ``route`` is "melody", "full" or "auto" (spec FR-A3).

    "auto" picks the full-mix route for chords or bands when it is installed, else the
    melody route with a warning.
    """
    from duet.audio import fullmix

    progress("decoding", 0.0)
    audio, sr = load_audio(path, DEFAULT_SR)
    progress("analysing", 0.1)
    if route == "auto":
        polyphonic = fullmix.looks_polyphonic(audio, sr)
        available = full_mix is not None or fullmix.full_mix_available()
        route = "full" if polyphonic and available else "melody"
        if polyphonic and not available:
            progress("transcribing:melody", 0.2)
            result = transcribe(audio, sr, transcriber)
            result.warnings.append(
                "this sounds like more than one voice; "
                "install the full-mix route for better results"
            )
            progress("ready", 1.0)
            return result
    if route == "melody":
        progress("transcribing:melody", 0.2)
        result = transcribe(audio, sr, transcriber)
        progress("ready", 1.0)
        return result
    if route != "full":
        raise ValueError(f"unknown route: {route}")
    full_mix = full_mix or fullmix.default_full_mix()
    progress("separating", 0.2)
    notes, stems = full_mix.transcribe_path(Path(path))
    progress("rhythm", 0.9)
    result = Transcription(
        notes=notes,
        tempo_bpm=estimate_tempo(notes, audio, sr),
        key=estimate_key(notes)[0],
        duration_s=round(audio.size / sr, 3),
        model=", ".join(stems) or full_mix.name,
        route="full",
    )
    if not notes:
        result.warnings.append("no notes found in any stem")
    progress("ready", 1.0)
    return result


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
