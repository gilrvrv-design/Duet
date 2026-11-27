"""Tempo, key and beat-grid quantisation for transcribed notes (spec §5.14 stages 5-7)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from duet.audio.notes import NoteEvent

_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def estimate_key(notes: Sequence[NoteEvent]) -> tuple[str, int, str]:
    """Krumhansl-Schmuckler key estimate from note durations: (name, tonic pitch class, mode)."""
    histogram = np.zeros(12)
    for n in notes:
        histogram[n.pitch % 12] += n.duration_s
    if not histogram.any():
        return "C major", 0, "major"
    best = max(
        (
            (np.corrcoef(histogram, np.roll(profile, tonic))[0, 1], tonic, mode)
            for tonic in range(12)
            for mode, profile in (("major", _MAJOR), ("minor", _MINOR))
        ),
        key=lambda r: r[0],
    )
    _, tonic, mode = best
    return f"{_NAMES[tonic]} {mode}", tonic, mode


def estimate_tempo(
    notes: Sequence[NoteEvent], audio: np.ndarray | None = None, sr: int = 22050
) -> float:
    """Beats per minute. Uses librosa's beat tracker on the audio when given, else the
    most common gap between note onsets, folded into 60-180 bpm."""
    if audio is not None and audio.size > sr:
        import librosa

        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
        value = float(np.atleast_1d(tempo)[0])
        if value > 0:
            return _fold(value)
    onsets = sorted({round(n.start_s, 3) for n in notes})
    gaps = np.diff(onsets)
    gaps = gaps[gaps > 0.1]
    if gaps.size == 0:
        return 100.0
    return _fold(60.0 / float(np.median(gaps)))


def _fold(bpm: float) -> float:
    while bpm < 60:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return round(bpm, 1)


def quantize(
    notes: Sequence[NoteEvent],
    tempo_bpm: float,
    grid_beats: float = 0.25,
    strength: float = 1.0,
    origin_s: float | None = None,
) -> list[tuple[float, float, NoteEvent]]:
    """(start beat, duration in beats, note) with starts pulled toward the grid.

    ``strength`` 0 keeps the played timing, 1 snaps fully (spec FR-A6 quantise strength).
    Beat 0 is ``origin_s`` (default: the first note).
    """
    if not notes:
        return []
    beat_s = 60.0 / tempo_bpm
    origin = min(n.start_s for n in notes) if origin_s is None else origin_s
    result = []
    for n in sorted(notes, key=lambda n: (n.start_s, n.pitch)):
        start = (n.start_s - origin) / beat_s
        end = (n.end_s - origin) / beat_s
        snapped_start = round(start / grid_beats) * grid_beats
        snapped_end = max(snapped_start + grid_beats, round(end / grid_beats) * grid_beats)
        s = start + (snapped_start - start) * strength
        e = end + (snapped_end - end) * strength
        result.append(
            (round(s, 6), round(max(e - s, grid_beats * (1 - strength) or grid_beats), 6), n)
        )
    return result
