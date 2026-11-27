"""Full-mix route (spec §5.14 FR-A3): separate a song into stems, then transcribe each.

Adapters for Demucs (separation) and Basic Pitch (polyphonic transcription) load their
libraries only when used, so the rest of Duet works without them. Install with
``pip install demucs basic-pitch`` (large: they bring PyTorch / TensorFlow or ONNX).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from duet.audio.io import DEFAULT_SR, load_audio
from duet.audio.melody import PyinTranscriber
from duet.audio.notes import NoteEvent, Transcriber

PITCHED_STEMS = ("vocals", "bass", "piano", "guitar", "other")


class RouteUnavailable(Exception):
    """The full-mix route's tools (Demucs, Basic Pitch, FFmpeg) are not installed."""


class SeparationFailed(Exception):
    """Demucs ran but failed."""


class Separator(Protocol):
    name: str

    def separate(self, path: Path) -> dict[str, np.ndarray]:
        """Stem name -> mono samples at DEFAULT_SR."""
        ...


def full_mix_available() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("demucs", "basic_pitch"))


def looks_polyphonic(audio: np.ndarray, sr: int, threshold: float = 0.25) -> bool:
    """True when many frames have three or more strong pitch classes (chords, a band).

    A single synthesized melody scores under 0.1; a melody over chords and bass for half
    the clip scores about 0.4.
    """
    import warnings

    import librosa

    if audio.size < sr // 2:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # short-window notices from the CQT
        chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
    loud = librosa.feature.rms(y=audio)[0]
    frames = chroma[:, : loud.size][:, loud[: chroma.shape[1]] > 0.02]
    if frames.size == 0:
        return False
    strong = (frames >= 0.5 * frames.max(axis=0, keepdims=True)).sum(axis=0)
    return float(np.mean(strong >= 3)) > threshold


@dataclass
class DemucsSeparator:
    """Runs the Demucs command line (htdemucs_6s: vocals, drums, bass, piano, guitar, other)."""

    model: str = "htdemucs_6s"
    name: str = "demucs-htdemucs_6s"

    def separate(self, path: Path) -> dict[str, np.ndarray]:
        with tempfile.TemporaryDirectory() as out:
            cmd = [sys.executable, "-m", "demucs", "-n", self.model, "-o", out, str(path)]
            result = subprocess.run(cmd, capture_output=True, check=False)
            if result.returncode != 0:
                raise SeparationFailed(
                    f"demucs failed: {result.stderr.decode(errors='replace')[-500:]}"
                )
            stem_dir = Path(out) / self.model / Path(path).stem
            return {wav.stem: load_audio(wav, DEFAULT_SR)[0] for wav in stem_dir.glob("*.wav")}


@dataclass
class BasicPitchTranscriber:
    """Spotify's Basic Pitch: polyphonic, instrument-agnostic notes."""

    name: str = "basic-pitch"
    min_note_s: float = 0.06

    def transcribe(self, audio: np.ndarray, sr: int) -> list[NoteEvent]:
        import soundfile
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            soundfile.write(tmp.name, audio, sr)
            _, _, note_events = predict(tmp.name, ICASSP_2022_MODEL_PATH)
        notes = [
            NoteEvent(
                round(float(start), 4),
                round(float(end), 4),
                int(pitch),
                int(np.clip(round(float(amp) * 127), 1, 127)),
                round(float(min(1.0, amp)), 3),
            )
            for start, end, pitch, amp, *_ in note_events
        ]
        return sorted(
            (n for n in notes if n.duration_s >= self.min_note_s),
            key=lambda n: (n.start_s, n.pitch),
        )


@dataclass
class FullMixTranscriber:
    """Separate, then transcribe each pitched stem with the best model for it."""

    separator: Separator
    polyphonic: Transcriber
    melodic: Transcriber = field(default_factory=PyinTranscriber)
    name: str = "full-mix"
    stem_rms_floor: float = 0.005

    def transcribe_path(self, path: Path) -> tuple[list[NoteEvent], list[str]]:
        notes, used = [], []
        for stem, audio in sorted(self.separator.separate(Path(path)).items()):
            if stem not in PITCHED_STEMS or float(np.sqrt(np.mean(audio**2))) < self.stem_rms_floor:
                continue  # drums are not pitched; skip near-silent stems
            model = self.melodic if stem in ("vocals", "bass") else self.polyphonic
            found = model.transcribe(audio, DEFAULT_SR)
            notes += [
                NoteEvent(n.start_s, n.end_s, n.pitch, n.velocity, n.confidence, stem)
                for n in found
            ]
            used.append(f"{stem}:{model.name}")
        return sorted(notes, key=lambda n: (n.start_s, n.pitch)), used


def default_full_mix() -> FullMixTranscriber:
    if not full_mix_available():
        raise RouteUnavailable("full-mix route needs: pip install demucs basic-pitch")
    if shutil.which("ffmpeg") is None:
        raise RouteUnavailable("full-mix route needs FFmpeg")
    return FullMixTranscriber(DemucsSeparator(), BasicPitchTranscriber())
