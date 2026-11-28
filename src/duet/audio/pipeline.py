"""Audio file -> Transcription -> MIDI (spec §5.14.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import mido

from duet.audio import fullmix  # its tools (Demucs, Basic Pitch) load only when used
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
    """The melody route: one voice, followed by pitch."""
    transcriber = transcriber or PyinTranscriber()
    notes = transcriber.transcribe(audio, sr)
    silent = "no notes found; is the recording silent or very noisy?"
    return _transcription(notes, audio, sr, transcriber.name, route, silent)


def _transcription(notes, audio, sr: int, model: str, route: str, silent: str) -> Transcription:
    """The result of either route, with what a person should know about it."""
    warnings = [] if notes else [silent]
    low = [n for n in notes if n.confidence < LOW_CONFIDENCE]
    if low:
        warnings.append(f"{len(low)} note(s) have low confidence")
    return Transcription(
        notes=notes,
        tempo_bpm=estimate_tempo(notes, audio, sr),
        key=estimate_key(notes)[0],
        duration_s=round(audio.size / sr, 3),
        model=model,
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
    progress("decoding", 0.0)
    audio, sr = load_audio(path, DEFAULT_SR)
    progress("analysing", 0.1)
    route, caution = _route(route, audio, sr, full_mix is not None or fullmix.full_mix_available())
    if route == "melody":
        progress("transcribing:melody", 0.2)
        result = transcribe(audio, sr, transcriber)
    else:
        full_mix = full_mix or fullmix.default_full_mix()
        progress("separating", 0.2)
        notes, stems = full_mix.transcribe_path(Path(path))
        progress("rhythm", 0.9)
        model = ", ".join(stems) or full_mix.name
        result = _transcription(notes, audio, sr, model, "full", "no notes found in any stem")
    if caution:
        result.warnings.append(caution)
    progress("ready", 1.0)
    return result


def _route(route: str, audio, sr: int, full_available: bool) -> tuple[str, str | None]:
    """The route to take, and what to tell the person about the choice (or None)."""
    if route not in ("auto", "melody", "full"):
        raise ValueError(f"unknown route: {route}")
    if route != "auto":
        return route, None
    if not fullmix.looks_polyphonic(audio, sr):
        return "melody", None
    if full_available:
        return "full", None
    caution = "this sounds like more than one voice; install the full-mix route for better results"
    return "melody", caution


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
