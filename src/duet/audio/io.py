"""Load any audio (or video) file as mono float samples (spec §5.14 FR-A1)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

DEFAULT_SR = 22050
NATIVE = {".wav", ".flac", ".ogg", ".aiff", ".aif"}
MAX_SECONDS = 15 * 60


class AudioError(ValueError):
    pass


def load_audio(path: str | Path, sr: int = DEFAULT_SR, max_seconds: float = MAX_SECONDS):
    """Return (samples, sr): mono float32 in [-1, 1], resampled to ``sr``."""
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"no such file: {path}")
    if path.suffix.lower() in NATIVE:
        audio, native_sr = _read_soundfile(path)
    else:
        audio, native_sr = _read_ffmpeg(path, sr), sr
    if audio.size == 0:
        raise AudioError("the file has no audio")
    if native_sr != sr:
        import librosa

        audio = librosa.resample(audio, orig_sr=native_sr, target_sr=sr)
    if audio.size / sr > max_seconds:
        raise AudioError(f"audio is longer than {max_seconds / 60:g} minutes")
    return audio.astype(np.float32), sr


def _read_soundfile(path: Path):
    import soundfile

    try:
        audio, sr = soundfile.read(str(path), dtype="float32", always_2d=True)
    except RuntimeError as exc:
        raise AudioError(f"cannot read {path.name}: {exc}") from exc
    return audio.mean(axis=1), sr


def _read_ffmpeg(path: Path, sr: int) -> np.ndarray:
    """Decode MP3, M4A, Opus, video files and the rest through FFmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioError(f"FFmpeg is needed to read {path.suffix} files")
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip().splitlines()
        raise AudioError(
            f"cannot decode {path.name}: {message[-1] if message else 'unknown error'}"
        )
    return np.frombuffer(result.stdout, dtype=np.float32)
